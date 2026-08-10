# Design Roadmap — from agent guardrail to repository prose layer

Where semantic-linefeeds is going, and why each decision was taken.

Every empirical claim here is reproducible from the corpus and commands in §3,
or from the packaging proof in `docs/proofs/zipapp-packaging/`.
Claims that could not be substantiated were removed rather than softened,
and §5 records the false-positive classes that survive in the shipped detector today.

## 1. The decisions

| Decision | Where |
|---|---|
| `long` never blocks an edit, and non-blocking findings use each host's model-visible protocol | §4 |
| `wrap` leaves default hook feedback; no positive-evidence predicate is adopted | §6 |
| Precision is measured against independent labels, never against detector output | §7 |
| The core stays one portable file; a separate CLI owns git, lifecycle, and rendering | §8 |
| Analysis sees the whole file; reporting is restricted to diagnostics a change owns | §9 |
| Every agent gets the judgment layer, not only the one with skills | §10 |
| Automatic repair is restricted to `!` and `?`, and prefers handing the fix back | §12 |

## 2. The governing constraints

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

## 3. Evidence base

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

## 4. The live contract violation

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

## 5. Known false-positive classes

Five classes are confirmed by direct reproduction.
All share one root cause:
a negative test with no positive evidence.

### 5.1 Confirmed classes

- **Non-connector continuations.**
  The `wrap` test flags unless the next line's first word sits in a 21-word list
  (`scripts/check_linefeeds.py:63-70`).
  The list is internally inconsistent:
  `until`, `while`, and `because` pass, while `once`, `after`, and `since` are flagged,
  though all six are subordinators.
- **Multi-letter abbreviations.**
  The `fused` regex accepts any lowercase token of two or more letters before terminal punctuation
  (`scripts/check_linefeeds.py:75-78`),
  so `vs.`, `cf.`, and `al.` split single sentences.
- **Trailing emphasis masks terminal punctuation.**
  A line ending `**Label.**` ends with `*`, absent from `OK_LINE_ENDERS` (`scripts/check_linefeeds.py:73`).
  Identical text without emphasis is clean.
- **Consecutive list items coalesce.**
  Markdown list markers are stripped without a paragraph break (`scripts/check_linefeeds.py:288-290`),
  so a bullet ending in `and` is measured against the next bullet.
- **Fragment paragraphs.**
  Adjacent short comment lines stay in one paragraph,
  so an unrelated terminated sentence can sit beside a candidate.

### 5.2 The emphasis repair must stay narrow

Stripping trailing emphasis **and** code markers would over-reach:
the backtick is already a legitimate ender (`scripts/check_linefeeds.py:73`),
so `` Current default: `value` `` is clean today,
and stripping code markers would turn it into a false positive.
Verified.

The repair peels **balanced closing emphasis delimiters only**, for the terminal-punctuation test alone.
Punctuation inside a code span is never exposed.
Handling for `*`, `**`, `_`, `__`, escapes, and unmatched delimiters is specified before implementation.

## 6. The `wrap` predicate

The retained audit and opt-in predicate keeps the existing mid-clause condition,
and no positive-evidence replacement is adopted.
This section records why three candidates were rejected,
and what any future candidate must clear before it can qualify a finding.

### 6.1 A rejected candidate: column clustering plus an absolute end column

One early candidate paired a column cluster over every non-final paragraph line with an absolute end-column floor.
This block defeats it:

```go
// Current release notes
// v2 remains supported.
// Future work is deferred.
```

Both of the first two lines end at column 24.
Line 1 is already a false positive today, because `v2` opens with a lowercase token outside the connector list.
The *terminated* second line would supply the second cluster point,
so clustering would have **manufactured evidence for an existing false positive** rather than rejecting it.

The absolute end column has a matching defect.
Raw length is rejected below because indentation distorts it,
and an absolute end column is distorted the same way:
for any finite floor, enough indentation lifts a short fragment over it.

### 6.2 Three candidates, three refutations

| Candidate signal | Kind | Defeated by |
|---|---|---|
| column clustering | geometric | a block of aligned labels |
| prose width | geometric | wide labels that no floor separates from real wraps |
| function-word termination | lexical | demonstratives, pro-forms, code tokens, non-English prose |

The third refutation is the one that generalizes.
All five of these are separate thoughts,
and the detector reports every upper line as `wrap` today:

```go
// Use this rather than that
// future calls receive the default.

// The accepted loop keyword is for
// compatibility depends on the parser mode.

// Die Einstellung bleibt so
// weitere Pruefungen sind unnoetig.
```

`that` is a demonstrative, `for` is an object-language token, and `so` is German.
A word list cannot tell those apart from a wrapper's stopping point,
because **lexical membership does not establish where meaning ends.**
Neither does geometry.
Establishing where meaning ends is the parsing problem this project has ruled out by charter.

### 6.2.1 The decision: `wrap` leaves default feedback

Three candidate predicates have now been refuted by counterexample,
each time within one review round.
That is no longer a run of bad luck;
it is evidence that a precise `wrap` is not reachable with the signals this project permits.

A noisy `wrap` is also worse than a missing one, and not merely by the usual asymmetry.
Its prescribed repair is to rejoin the severed clause (`skills/semantic-linefeeds/SKILL.md:38`).
Applied to a false positive, that instruction **destroys a correct semantic line break**
and pushes the prose back toward the long lines this project exists to eliminate.
A false `wrap` therefore does not just annoy;
it actively reverses the tool's purpose.

So v0.4.1 withdraws `wrap` from default model-visible feedback:

- **Hook feedback** reports `fused` only.
  `fused` is the precise kind once abbreviations are excluded, and it stays blocking.
- **`--file` audits** still report `wrap`, because there a human asked for it.
- **Hook `wrap` reporting** returns only behind an explicit opt-in, for evaluation.

This is a recall reduction taken deliberately,
and it is the project's own rule applied without flinching:
a miss is acceptable, a false positive is a bug (`.agents/rules/100-project-map.md:25-31`).

`fused` does **not** catch most column-wrapped paragraphs.
Measurement points the other way:
of 781 reference-corpus paragraphs carrying a `wrap` finding, 286 also carry a `fused` finding, or 36.6%.
An independent count over slightly different paragraph segmentation gave 37.4%.

Both numbers are detector-output correlation, not labeled recall,
so neither proves nor disproves coverage of genuinely column-wrapped paragraphs;
§3's prohibition applies to them exactly as it does to every other raw count.
The fixtures show only that the two defects often coexist —
7 of 9 marked `wrap` paragraphs also carry `fused`, and
`tests/fixtures/go/bad_wrapped.go:1` carries both on one line.

So the honest statement is:
paragraph-level retention is **unknown** until §7 supplies independent labels.
The corpus records, for every labeled true `wrap` paragraph,
whether it also contains an independently valid `fused` finding,
and reports that by the existing strata.
That measurement, not an estimate, decides how much this withdrawal costs.

### 6.2.2 The withdrawal ships atomically with the abbreviation exclusions

`fused` is not safe as the sole blocking kind *today*.
Each of these is a single sentence, and the detector reports each as `fused`:

```text
Compare TCP vs. UDP behavior.
For background, cf. Figure 2.
```

This roadmap tripped the same defect while documenting it,
which is its own small argument for the atomicity rule below.

So the withdrawal must not ship before the §14 abbreviation exclusions.
Both land in the same commit, with a release-level test asserting they become visible together.
The v0.4.1 commit order is otherwise unaffected,
because its first group repairs `long` while leaving the blocking-kind set exactly as it is.

### 6.2.3 The hook-output matrix

"Default hook feedback reports `fused` only" is ambiguous read literally,
since it would also silence the `long` advisory that v0.4.1's first commit group has just repaired.
The full contract is therefore stated once, here:

| Result | Default hook behavior |
|---|---|
| `fused` | Exit 2, blocking feedback |
| `long` only | Exit 0, host-native advisory output |
| `wrap` only | Exit 0, no output |
| `fused` plus `long` | Exit 2, one combined report |
| `wrap` plus another kind | Drop `wrap`, then apply the rule for what remains |

The opt-in surface is an environment variable, `SEMLF_EXPERIMENTAL_WRAP`,
because hooks pass only `--hook <agent>` today
(`hooks/hooks.json:5-9`, `adapters/codex/hooks.json:5-9`)
and project configuration does not arrive until v0.6.
Opt-in `wrap` exits 0, and it never reuses the repair wording:
it is evaluation output, so it must not instruct the model to rewrite anything.
opencode renders it through the same advisory path as `long`.

These are updated in the same release:
the module docstring, CLI help, README, project map, and every adapter contract.

### 6.2.4 The condition for `wrap` to return

`wrap` returns to default feedback when, and only when, some predicate reaches
**zero false positives on a held-out labeled set** under the §7 protocol.
Until then it is an experiment, not a diagnostic.
If no predicate ever clears that bar, `wrap` stays out, and that is an acceptable outcome.

Everything already refuted stays refuted:
clustering, width floors, and bare word lists are all closed.
Re-proposing any of them requires a structural discriminator for token use, hard line breaks, and human language.

### 6.3 Calibration, not constants

No `wrap` predicate constants remain in this plan, because no predicate survives to be calibrated.
The §7 protocol governs any future candidate, and §7.4 states the one-shot holdout rule that protects it.

One tab width is documented before implementation, since expansion decides every column.
The Markdown extractor skips four-space lines and strips at most one blockquote and one list marker
(`scripts/check_linefeeds.py:263-265`, `scripts/check_linefeeds.py:288-290`),
so deeply nested prose never enters the paragraph stream.
Either extraction is extended, or nested prose is documented as out of scope.

## 7. The evaluation contract

### 7.1 A positive denominator independent of the detector

Candidates generated from current detector output would exclude every violation the detector already misses,
making recall unfalsifiable.
So the known-positive corpus is built independently:
by sampling prose regardless of detector verdict, then labeling.

- Every candidate is labeled true, false, or ambiguous.
- Ambiguous cases are excluded from rates and retained as qualitative cases.
- Recall is detected true violations over the **frozen** true-violation denominator, per kind and stratum.
- Calibration and holdout sources stay separate.
- Strata for `wrap`: prose width, raw end column, indentation depth, language,
  Markdown nesting, trailing inline markup, list-item adjacency,
  paragraph line count, and eligible-anchor count.
  The last two are the dimensions any future clustering signal would move,
  so they are stratified before such a signal is considered.

### 7.2 Gates

- Zero false positives on calibration and holdout.
- Per-kind, per-stratum recall floors, **frozen before the parameter grid runs**,
  as either absolute counts or a maximum permitted drop from a recorded baseline.
  A floor chosen after seeing results is not a gate.
- Every new accepted miss fails the build until a reviewer approves a manifest change,
  so the accepted-miss list bounds future losses instead of merely recording past ones.
- Exact `(line, kind)` identity assertions, extending the marker mechanism
  (`tests/conftest.py:19-32`, `tests/test_detector.py:16-21`).
- Mutation sensitivity: removing any evidence rule, connector, or abbreviation exclusion must fail a specific test,
  rather than merely moving a total.

### 7.4 One-shot holdout

Selecting parameters against calibration **and** holdout would use the holdout for model selection,
so it would stop being an independent test,
and predeclaring the grid does not repair that leakage.

The protocol is therefore:

1. Select every parameter using calibration data alone.
2. Freeze the exact words, tokenization, case normalization, markup handling,
   and any corroboration rule, with a manifest digest.
3. Open the holdout once and evaluate the frozen predicate.
4. A holdout failure rejects that candidate,
   and any further tuned attempt requires a **new, untouched** holdout.

Tooling enforces this: the calibration harness cannot read the holdout
until the predicate and manifest digest are frozen.

Any signal that changes whether a diagnostic exists is a qualifier, not corroboration,
and must clear this protocol in full.

### 7.3 The fixture decision, corrected

The marked `wrap` fixtures do not all sit at narrow widths.
After marker removal, the Go anchors end at 77 and 74
(`tests/fixtures/go/bad_wrapped.go:1`, `tests/fixtures/go/bad_wrapped.go:4`),
and both Markdown anchors end at 75 (`tests/fixtures/markdown/bad_wrapped.md:3-4`).
Those four are exactly the four that survive a 65-column gate;
the claim held only for the eleven that do not.

Rewriting the short fixtures in place would erase the evidence needed to audit the recall trade,
which is moving the goalposts.

Corrected decision:

- Short fixtures are **preserved**, moved to an accepted-miss manifest with their expected status.
- Realistic-width positives are **added alongside**, not substituted.
- Every labeled true violation carries a frozen detected-or-accepted-miss status.

## 8. The portable core boundary

`.agents/rules/100-project-map.md:17-23` requires one Python 3.9+ stdlib-only core,
because every adapter copies and runs that file.
The core is at 747 lines against a ~1000-line split point.

### 8.1 The split, and a packaging proof

- **Portable core** (`scripts/check_linefeeds.py`) keeps extraction, predicates, suppression semantics,
  span filtering, diagnostic construction, and the hook entry points.
- **Repository CLI** (`semlf`) owns git snapshot selection, subcommand routing,
  installation lifecycle, doctor, and SARIF rendering.
  Config *discovery* is not on this list;
  §8.2 places it in the core, and the CLI reuses that one function.

A proof of concept validates that this split is shippable as one artifact.
`python -m zipapp` produced a **10,465-byte** `semlf.pyz`,
carrying a core byte-identical to the repository copy, verified by `cmp`.

| Property | Result |
|---|---|
| Runs from an empty directory under `python3 -I -S` | Correct findings, exit 1 |
| Hook mode through the same artifact | exit 2, output identical to the core |
| `check --staged` against a divergent worktree | Reported the staged blob, ignored the clean worktree |
| Core copied alone, without the zipapp | Still runs, exit 1 |
| Python 3.9 syntax | All four modules parse at `feature_version=(3,9)` |
| Imports | `argparse collections json os re subprocess sys tempfile`, all stdlib |
| Startup cost | 22.6ms versus 16.4ms, median of 25 runs each, CPython 3.12.3, one machine |

The build recipe, the module sources, and the staged-repository fixture are checked in at
`docs/proofs/zipapp-packaging/`,
with the embedded core's digest as the identity check,
so the proof is reproducible rather than reported.
The archive's own digest is deliberately not asserted,
because `zipapp` embeds modification times and it therefore varies between builds.
One command rebuilds the artifact and replays the functional boundary rows.
The isolated-run row is asserted by exit status rather than by finding identity,
and the startup timing row is recorded separately rather than replayed.

Two limits are recorded honestly:
3.9 was checked for **syntax only**, since no 3.9 interpreter was available;
and the 6.2ms zipapp overhead is irrelevant for a CLI but would need re-evaluation
if hooks were ever routed through the archive.

The vague line-count threshold is replaced by executable tests:
copy the core alone into an empty directory, replay every adapter payload,
run it under Python 3.9, and reject any import outside a stdlib allowlist.

### 8.2 Hook configuration discovery

Every adapter invokes the core **without** the repository CLI
(`hooks/hooks.json:5-9`, `adapters/codex/hooks.json:5-9`,
`adapters/opencode/semantic-linefeeds.ts:42-60`).
Leaving policy discovery to the CLI alone would let hooks and CI disagree,
which is the failure that destroys trust in a linter.

Decision: the **core** carries one small stdlib-only discovery function,
with an explicit start directory, precedence order, and parse-failure behavior.
The CLI reuses it rather than owning a second one.
Hook and CLI tests run against the same parsed configuration model.

## 9. The changed-span model

Unifying the three entry points on `check(full_text, path, changed_spans)`
gives context-awareness, real Codex line numbers, and one contract for the git modes.

### 9.1 Three ranges, not two

v2 used anchor plus evidence and reported on evidence intersection.
That alone does not preserve the invariant:
an unchanged candidate boundary can be reported once a newly edited sentence becomes its supporting evidence,
even though the accused line break itself never changed.

Every diagnostic therefore carries:

- an **anchor range** — where it is displayed;
- an **evidence range** — all context used to establish it;
- an **ownership range** — the accused physical boundary itself.

Ownership by kind:

| Kind | Ownership range |
|---|---|
| `wrap` | the upper line's terminal token, the newline boundary, and the lower-line opening token |
| `fused` | the complete regex match, through the right-hand opening token |
| `long` | the changed prose line |

Ownership covers **local causal text**, not only the physical separator.
For `fused`, lowercasing to uppercase on the right-hand side can create a match
that punctuation-only ownership never sees (`scripts/check_linefeeds.py:75-78`),
so ownership runs through the right-hand opening token.
For `wrap`, no ownership exists in **default hook output**, since no `wrap` reaches it.
The retained predicate still produces findings in `--file` audits and in opt-in evaluation,
so those modes use the range in the table above,
and any replacement predicate must redefine ownership when it is introduced.
Width never appears in ownership, since §6.2.1 leaves it qualifying nothing.

**A diagnostic is reported only when its ownership range intersects a changed span or boundary.**
Preimage comparison is a second condition, never a substitute.
Ranges are defined over Unicode code points,
with explicit rules for zero-width intersection and discontiguous evidence.

### 9.2 Span sources

| Source | Rule |
|---|---|
| Edit, `new_string` found once | Map to that span |
| Edit, found zero or several times | Payload-only fallback |
| `replace_all: true` | Spans only from a preimage or a tool-supplied diff |
| Write | `content` is both context and a whole-file span |
| Codex patch | Match full hunk context against a stable post-state; else addition-run fallback |
| `--staged` | The index blob, never the worktree |

Changed spans are half-open after-state ranges plus zero-width boundaries,
because deleting a newline can create a `fused` violation no added-line range represents.
Every span records whether its mapping is exact or degraded.
The core reads one stable snapshot and detects modification during the read;
on any mismatch or degraded mapping it falls back to payload-only checking.
**The existing snippet mode is retained as that fallback, not deleted.**

`.agents/rules/100-project-map.md:27-34` is amended in the same change,
restated as: analysis may see the whole file;
reporting is restricted to diagnostics **owned** by a change.

## 10. The judgment layer, for every agent

The three-layer design is installed only for Claude Code today.
The Codex installer adds the hook and nothing else (`scripts/install.py:69-108`),
its guide leaves the 12-line snippet an optional step (`adapters/codex/INSTALL.md:20-24`),
and the opencode skill must be copied by hand (`adapters/opencode/INSTALL.md:11-20`).
Meanwhile the hook tells every agent to load a skill (`scripts/check_linefeeds.py:582`).

Codex CLI resolves standalone `SKILL.md` skills from a repository `.agents/skills` directory
and from `$HOME/.agents/skills`;
the user-level directory exists and is populated on this machine,
though only the directory convention was verified locally, not the end-to-end load.

- The Codex installer **installs the native skill**, and covers status, upgrade, and uninstall for it.
- `SNIPPET.md` gains the compound-object `and` test, the clause-boundary definition,
  and the never-break list, and remains the fallback for agents that genuinely have no skill mechanism.
- Hook feedback names a judgment layer only when the installer actually supplied one.
- Hook feedback carries a **suggested diff** rather than only a description,
  since agents act on concrete replacements more reliably than on prose instructions.
  This shares its mechanism with §12 fix delivery.

## 11. Suppression, and operational contracts

Suppression ships **with** the release that widens hook visibility, never after it.
Its contract is specified before that release:
directive syntax, scope, nesting, malformed-state behavior, protected-context handling,
and interaction with changed spans and ownership ranges.

`uninstall` ships with the first packaged lifecycle command.
`doctor` ships before team integration,
and it replays a synthetic payload end to end rather than checking that files exist.

## 12. Fixability classes

`fused` misfires on abbreviations, so a period boundary cannot be proven safe by an allowlist,
which is open by construction.
Three entries proposed earlier — `Fig.`, `No.`, `Eq.` —
cannot match the current case-sensitive regex at all (`scripts/check_linefeeds.py:75-78`).

- Period-based `fused` stays a **suggestion**.
- The first automatic class is restricted to `!` and `?`, after protected-span checks.
- Any fix reconstructs raw source, preserving markers, indentation, block prefixes, quoting,
  and newline style, and is byte-identical outside the replacement.
- A content hash is compared immediately before writing.
- **Preferred delivery is an exact replacement handed back for the agent's next edit.**
  Hook-side mutation stays deferred until adapters can force a file-view refresh.

## 13. Principles

1. **Meaning before columns.**
2. **Long is better than broken**, and the enforcement path must honor that too.
3. **Check changes, not history.**
4. **Precision before recall, measured against labels rather than asserted.**
5. **Suggest before rewriting.**
6. **Suppression is an escape hatch, never a substitute for precision.**
7. **Integration failure must not break the agent.**
8. **Every agent gets the same judgment layer, not only the one with skills.**

## 14. Releases

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

## 15. Deferred, with reasons

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

## 16. Positioning

> A diff-aware prose guardrail for AI coding agents and source repositories.

The README should drop its explanation of *why* models emit column-wrapped prose.
That is a hypothesis the project does not need.
The load-bearing claim is narrower and demonstrable:
agents produce non-semantic line breaks,
instructions alone do not reliably prevent it,
and a deterministic check at the tool boundary catches it.
