# Corpus

Text used to measure the detector rather than to be read.
Nothing here is documentation,
and the self-hosting rule in [`AGENTS.md`](../../AGENTS.md) does not apply to it.

## `compliant/`

Prose that already follows the convention.
Every finding against a file in this directory is a false positive by construction,
which is what makes the directory useful:
it is the set the detector must stay silent about.

Each file holds one class of mistake the detector is known to make,
and every case was reproduced against the checker before it was added here.
Cases invented from a description, without running them, do not belong.

Every class here was found by something else first.
This directory holds what the project knows about,
and the four classes the holdout round turned up were found by labelers arguing over a boundary,
not by any file in it.
[ADR-0008](../../docs/decisions/0008-a-holdout-is-spent-by-being-opened.md) records that.

| File | The class it holds |
|---|---|
| `go/aligned_labels.go` | Label lines that end at a shared column |
| `go/lexical_continuations.go` | Demonstratives, object-language tokens, non-English prose, subordinators |
| `go/fragment_paragraphs.go` | A short heading fragment beside a terminated sentence |
| `go/wide_labels.go` | Labels too wide for any width floor to separate from a real wrap |
| `markdown/abbreviations.md` | Multi-letter abbreviations read as sentence ends |
| `markdown/trailing_emphasis.md` | Emphasis markup hiding the terminal punctuation behind it |
| `markdown/adjacent_list_items.md` | One list item measured against the next |
| `markdown/release_notes.md` | Release-note fragments in Markdown rather than comments |

Four of these eight classes were repaired in v0.4.1 and the files stay,
because a class nothing tests is a class that comes back.
The four label classes are the ones that remain,
and they are the reason `wrap` no longer reaches the model.

## `control/`

One file the detector must complain about.

The compliant gate asserts silence,
and silence is also what a gate that checked nothing produces.
Hook mode skips whole classes of path, the platform temp directory among them,
so a checkout under that directory makes every compliant file invisible.

`control/fused.go` is the positive control.
When it draws no complaint the gate reports that it is blind,
rather than reporting that the prose passed.
It is the one file here that must never be repaired.

## `known_false_positives.json`

What the detector reports against `compliant/` today, by file, line, and kind.

It is a record, not a target.
The gate fails when the record and reality disagree in **either** direction,
because a case that was silently fixed is as worth knowing about as one that appeared.
Regenerate it deliberately, never to make a red test go green.

## `repairs/`

A second corpus beside the first, sharing its instrument rather than copying it.

The first corpus measures whether a finding is correct.
This one measures what happens next:
given a `fused` finding delivered the way the hook delivers one,
what does a repairing agent do with the line, and was it right.

**Its units are conditional on delivery.**
The population is every `fused` boundary the detector raises on the calibration sources,
not every prose boundary in them.
A repair exists only where a finding was delivered.
That conditional is what the corpus measures,
and it is not the denominator [ADR-0003](../../docs/decisions/0003-precision-measured-against-labels.md) forbids:
the detector's firing is in the condition rather than in the denominator,
and a finding the detector never raises has no repair to measure.

**Its strata are exact sets of withholding classes.**
Class membership overlaps, so a quota on one class biases another class's marginal.
Exact sets are disjoint, so the draw has known inclusion probabilities
and a class marginal is a weighted derived report labelled as one.

**Its unit is a window of one or two judged lines**, not a boundary,
because the repair that matters rejoins before it splits.
Leaving the window alone is a candidate like any other,
so a finding whose right answer is to change nothing is an outcome here rather than a hole.

**What it does not measure.**
A pass is shown the report body the checker renders,
and not the suggested replacement a host appends beside it.
So the defect rates describe agents given a blinded body rather than full hook feedback.
They are a floor on how well agents repair, not an estimate of it.

And nothing in it admits a class.
Every number here is measured on the calibration side,
and admission is scored on a holdout round drawn after a widened predicate is frozen
([ADR-0023](../../docs/decisions/0023-what-a-repair-corpus-measures.md)).

## `manifest.json`

Everything a reviewer needs to recompute a reported rate without trusting the run that produced it:
the sources and how they were selected,
the rules that decide when a rate may be printed at all,
the digest of the published rule the labels were judged against,
and one record per labeled unit: its text, its nine covariates, its three blind passes, and its frozen expected status.

It holds twelve sources and 718 unit records over 359 boundaries:
three on the calibration side and nine holdout sources across three rounds.
Every unit record is from the calibration side.
The holdout sources carry no unit records at all:
their labels live inside a sealed bundle and never in the working tree.

A holdout source also declares the round it belongs to.
Round 1 is spent — the sessions that repaired what it found have read all three of its sources —
and the validator refuses a holdout source that names no round,
so a later draw cannot quietly enumerate one of them again.

It also holds the recall floors:
one per kind for the corpus entire, one per level for every stratum that can carry a rate,
and the floors each holdout round must clear, stated before that round was drawn.

The holdout floors are keyed by round.
The calibration rates a floor is derived from move as the detector is repaired,
so one floor covering every round would have to be restated once a round had already answered it.

A floor a round missed is recorded beside them,
naming what the miss is attributed to and what it blocks.
The suite fails when a round misses a floor and nothing here says so,
because the `floors_met` a result file records is otherwise consulted by nothing
and a missed prediction is then read by the next reader as a pass.

## `calibration/`, `pilot/`, and `labeled/`

`pilot/` is the first 48 boundaries, drawn on one stratum to measure the prevalence that sets the sample size.
`calibration/` is the corpus itself.
Each holds the drawing script and the sample it drew,
so a reviewer redraws rather than trusting the run that produced it.

`labeled/NOTICE.md` lists every source project, its licence, and its copyright line as that project states it.

The tooling beside them is shared:
`batch.py` splits a sample into per-labeler batches,
`collect.py` gathers three passes into one file,
`promote.py` resolves them into labels,
and `adjudicate.py` carries what the resolution table sends to a person.

## `qualify.py`

The measurement a source is admitted on, and nothing else.

It reports the column a project wraps at, from line lengths alone.
Nothing in it reads the detector:
choosing a repository by how many findings it draws would repeat, at repository granularity,
the error [ADR-0003](../../docs/decisions/0003-precision-measured-against-labels.md) forbids at candidate granularity.

The first six sources were qualified by a script nobody kept,
which is why this one exists.
Their recorded columns stand as recorded;
the manifest's protocol notes say how far a replay of this instrument lands from each of them.

## `manifest.lock`

The digest of `manifest.json`, and one line saying why it last changed.

Editing the manifest without repinning the lock turns the suite red,
which is what makes a new accepted miss an act somebody signs rather than a line that appears.

## `freeze.jsonl`

Append-only, committed, and written only by the harness.
A freeze record names the predicate, the calibration manifest, and the sealed holdout an evaluation intends to open;
the result is appended afterwards against that same record.

A bundle's freeze can only be written once the bundle exists,
which is after its prose has been drawn, labeled, and sealed.
So a round opens with a second kind of record that names a predicate and nothing else:
the draw refuses to run without it, and so does the seal.
That one is the prediction, and the bundle's freeze binds a ciphertext to it afterwards.

The file does not exist until the first freeze.
Nothing hand-edits it: a rewritten line would let a run restate what it froze after reading the holdout.

## [`../corpus_harness.py`](../corpus_harness.py)

The sealed holdout, the schema validator, and the rule that turns three blind labeling passes into one label.

The holdout is committed as ciphertext because plaintext in the working tree is read by the agent doing the tuning.
Opening it is refused unless the ledger already froze this predicate against this bundle,
and refused again once that bundle has been evaluated.
Sealing one is refused for a predicate the ledger never froze,
which is the ordering the first round kept by hand.
The refusals are proven by mutation rather than by a passing test:
opening the ledger for write instead of append,
sealing with a fixed salt,
and keeping a debug copy of the plaintext each kill a named test.

## How the gate reads all this

[`../test_corpus.py`](../test_corpus.py) asks what a host would show the model,
rather than what `check()` returns.
The two differ:
a kind can keep appearing in `--file` audits after it stops reaching the model,
and a diagnostic nobody is shown costs nobody anything.

The goal is that no file here draws any complaint at all, and v0.4.1 reached it.
The gate was an expected failure until then, marked strict,
so the day the defects were repaired it failed for passing and the marker could not be left behind.
That is how it came off.

Eleven `wrap` findings against this corpus survive in `check()` and stay in the record above.
They are the evidence the withdrawal rests on rather than a leftover:
correct prose that a kind still complains about is the reason that kind no longer reaches the model.
