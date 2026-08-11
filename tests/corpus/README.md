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

## `manifest.json`

Everything a reviewer needs to recompute a reported rate without trusting the run that produced it:
the sources and how they were selected,
the rules that decide when a rate may be printed at all,
the digest of the published rule the labels were judged against,
and one record per labeled unit: its text, its nine covariates, its three blind passes, and its frozen expected status.

It holds no source and no unit yet.
The reporting rules and the pinned rule are settled;
sampling has not started.

## `manifest.lock`

The digest of `manifest.json`, and one line saying why it last changed.

Editing the manifest without repinning the lock turns the suite red,
which is what makes a new accepted miss an act somebody signs rather than a line that appears.

## `freeze.jsonl`

Append-only, committed, and written only by the harness.
A freeze record names the predicate, the calibration manifest, and the sealed holdout an evaluation intends to open;
the result is appended afterwards against that same record.

The file does not exist until the first freeze.
Nothing hand-edits it: a rewritten line would let a run restate what it froze after reading the holdout.

## [`../corpus_harness.py`](../corpus_harness.py)

The sealed holdout, the schema validator, and the rule that turns three blind labeling passes into one label.

The holdout is committed as ciphertext because plaintext in the working tree is read by the agent doing the tuning.
Opening it is refused unless the ledger already froze this predicate against this bundle,
and refused again once that bundle has been evaluated.
Both refusals are proven by mutation rather than by a passing test:
opening the ledger for write instead of append,
sealing with a fixed salt,
and keeping a debug copy of the plaintext each kill a named test.

## How the gate reads all this

[`../test_corpus.py`](../test_corpus.py) asks what a host would show the model,
rather than what `check()` returns.
The two differ:
a kind can keep appearing in `--file` audits after it stops reaching the model,
and a diagnostic nobody is shown costs nobody anything.

The goal is that no file here draws any complaint at all.
That test is expected to fail today and is marked so.
The marker is strict,
so the day the defects are repaired it fails for passing
and cannot be left behind.
