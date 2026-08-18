# ADR-0002: `wrap` leaves default hook feedback

**Status:** accepted  
**Date:** 2026-08-10
**Amended:** 2026-08-14 —
[ADR-0017](0017-experimental-wrap-also-lives-in-ini.md) adds a `.semlf.ini` `experimental-wrap` key beside the environment variable;
the opt-in-surface sentence below now names one of two surfaces,
env still winning over ini.
**Amended:** 2026-08-18 —
[ADR-0021](0021-a-withheld-finding-travels-with-the-block-it-shares-a-line-with.md) adds one exception to the withdrawal below:
a `wrap` anchored on a line a blocking finding already holds is delivered with it,
because that line is being rewritten either way.
Every line no block holds keeps the withdrawal exactly as stated here.

## Context

Five classes are confirmed by direct reproduction.
All share one root cause:
a negative test with no positive evidence.

### Confirmed classes

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

### The emphasis repair must stay narrow

Stripping trailing emphasis **and** code markers would over-reach:
the backtick is already a legitimate ender (`scripts/check_linefeeds.py:73`),
so `` Current default: `value` `` is clean today,
and stripping code markers would turn it into a false positive.
Verified.

The repair peels **balanced closing emphasis delimiters only**, for the terminal-punctuation test alone.
Punctuation inside a code span is never exposed.
Handling for `*`, `**`, `_`, `__`, escapes, and unmatched delimiters is specified before implementation.

The retained audit and opt-in predicate keeps the existing mid-clause condition,
and no positive-evidence replacement is adopted.
This section records why three candidates were rejected,
and what any future candidate must clear before it can qualify a finding.

### A rejected candidate: column clustering plus an absolute end column

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

### Three candidates, three refutations

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

### The decision: `wrap` leaves default feedback

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
The prohibition in ADR-0003 applies to them exactly as it does to every other raw count.
The fixtures show only that the two defects often coexist —
7 of 9 marked `wrap` paragraphs also carry `fused`, and `tests/fixtures/go/bad_wrapped.go:1` carries both on one line.

So the honest statement is:
paragraph-level retention is **unknown** until ADR-0003 supplies independent labels.
The corpus records, for every labeled true `wrap` paragraph,
whether it also contains an independently valid `fused` finding,
and reports that by the existing strata.
That measurement, not an estimate, decides how much this withdrawal costs.

### The withdrawal ships atomically with the abbreviation exclusions

`fused` is not safe as the sole blocking kind *today*.
Each of these is a single sentence, and the detector reports each as `fused`:

```text
Compare TCP vs. UDP behavior.
For background, cf. Figure 2.
```

This roadmap tripped the same defect while documenting it,
which is its own small argument for the atomicity rule below.

So the withdrawal must not ship before the `fused` abbreviation exclusions.
Both land in the same commit, with a release-level test asserting they become visible together.
The v0.4.1 commit order is otherwise unaffected,
because its first group repairs `long` while leaving the blocking-kind set exactly as it is.

### The hook-output matrix

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

### The condition for `wrap` to return

`wrap` returns to default feedback when, and only when, some predicate reaches **zero false positives on a held-out labeled set** under the ADR-0003 protocol.
Until then it is an experiment, not a diagnostic.
If no predicate ever clears that bar, `wrap` stays out, and that is an acceptable outcome.

Everything already refuted stays refuted:
clustering, width floors, and bare word lists are all closed.
Re-proposing any of them requires a structural discriminator for token use, hard line breaks, and human language.

### Calibration, not constants

No `wrap` predicate constants remain in this plan, because no predicate survives to be calibrated.
ADR-0003 governs any future candidate, and its one-shot holdout rule protects it.

One tab width is documented before implementation, since expansion decides every column.
The Markdown extractor skips four-space lines and strips at most one blockquote and one list marker
(`scripts/check_linefeeds.py:263-265`, `scripts/check_linefeeds.py:288-290`),
so deeply nested prose never enters the paragraph stream.
Either extraction is extended, or nested prose is documented as out of scope.

## Consequences

- Recall falls, deliberately.
  The project's rule is that a miss is acceptable and a false positive is a bug
  (`.agents/rules/100-project-map.md:25-31`).
- The withdrawal must ship in the same change as the `fused` abbreviation exclusions,
  because `fused` is not safe as the sole blocking kind before them.
- Any future candidate predicate must clear a held-out labeled set at zero false positives,
  under ADR-0003, before it can qualify a finding.
