# Documentation

Organized by lifecycle rather than by topic,
because what decides whether a document can still be trusted is how it ages,
not what it is about.

| Directory | Holds | Lifecycle |
|---|---|---|
| [`ROADMAP.md`](ROADMAP.md) | What has not shipped yet | Living; shrinks as releases ship |
| [`DETECTOR_SPEC.md`](DETECTOR_SPEC.md) | What the portable detector currently implements | Living; changes with detector behavior |
| [`decisions/`](decisions/) | Why the design is what it is | Immutable once accepted; superseded, never edited |
| [`plans/active/`](plans/active/) | Work being executed now | Living until its release ships |
| [`plans/done/`](plans/done/) | Plans that were executed | Frozen history |
| [`research/`](research/) | Investigation snapshots | Frozen; true as of their date |
| [`proofs/`](proofs/) | Executable evidence for a claim | Runnable; kept working |

## Where to start

- **Changing the detector or an adapter?**
  Read [`.agents/rules/`](../.agents/rules/) first — those are the rules in force.
  Reach for [`decisions/`](decisions/) only when a rule seems wrong,
  since that is where the reasoning behind it lives.
- **Planning work?**
  [`ROADMAP.md`](ROADMAP.md) says what is next and in what order.
- **Wondering whether a document is still true?**
  Its directory answers that before you read a word of it.

## Naming

- Living documents take a stable name, with no date.
  A date on a file that is edited weekly records when it was started, which is rarely what a reader wants.
- Immutable records take a date prefix, because the date is part of what they mean.
- Decision records take a sequence number, because they are cited by number,
  and because the order decisions were taken matters more than the calendar.

## What belongs where

A release that ships moves out of `ROADMAP.md` and into `CHANGELOG.md`.
The roadmap describes the future; the changelog describes the past.
Neither should describe both.

A plan that finishes moves from `plans/active/` to `plans/done/` unchanged.
It is kept because it records what was intended,
which is what makes a later surprise diagnosable.
