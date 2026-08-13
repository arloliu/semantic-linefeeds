# ADR-0010: Suppression is a stateless single-line directive

**Status:** accepted
**Date:** 2026-08-12
**Amended:** 2026-08-12 —
carrier identification and recognition are two steps:
the extractor marks a candidate by yielding it in the prose stream,
and what it suppresses is read only after the licence cut,
so a candidate inside a removed paragraph is never read as a directive.

## Decision

Two directives, each scoped to exactly one line:

- `semlf-ignore` — withholds every diagnostic **anchored** on the line carrying it.
- `semlf-ignore-next` — withholds every diagnostic anchored on the following raw line.

There is no block form, no range form, and no file-level switch.
A stateless line cannot be left unclosed,
so the malformed-state class that block suppression drags in — an `off` nobody turned back `on`,
silently swallowing every finding to the end of the file — cannot exist here at all.

### Grammar

A directive is this, case-sensitively, with nothing else in its carrier:

```
directive = name (WS+ kind)*
name      = "semlf-ignore-next" | "semlf-ignore"
kind      = "fused" | "wrap" | "long"
```

- `WS` is the ASCII space or horizontal tab, nothing wider.
  Optional `WS` is accepted after the comment leader, between tokens, and before the closing marker;
  trailing `WS` at the end of the raw line is trimmed before any carrier matching.
- The longer name wins:
  `semlf-ignore-next` is one name,
  never `semlf-ignore` trailed by an unknown `-next` argument.
- A name or kind must be delimited by whitespace, the carrier's ends, or the carrier's closing marker;
  `semlf-ignored` and `SEMLF-IGNORE` are not directives and read as ordinary text.
- An empty argument list suppresses every kind;
  `semlf-ignore-next fused` narrows the suppression to one kind.
- A duplicate kind is idempotent, not an error.
- A closing comment marker that matches the carrier's opener
  (`-->` for `<!--`, `*/` for `/*`, `#>` for `<#`, `]]` for `--[[`, `-}` for `{-`)
  is carrier syntax, stripped before the arguments are read, never an argument itself —
  so `<!-- semlf-ignore -->` is well-formed and `-->` is not an unknown token.
- One directive per carrier;
  a second directive name in the argument list is an unknown token like any other.

A recognized name whose argument list carries any unknown token is **malformed and wholly inert**:
it suppresses nothing, of any kind.
Partially honoring a typo would hide the author's intent behind a half-working line;
an inert directive leaves the findings visible,
and visible findings are what prompt the author to look at the line again.
A malformed directive introduces no new diagnostic kind in this release;
surfacing them through a doctor-style command is recorded below as a non-decision.

### Where a directive is recognized

A carrier is identified while the extractor walks the file,
on the lines it reads as prose or comment surface,
in exactly two carrier forms:

- **Standalone**: a line whose extracted content is exactly one directive.
  This covers a full comment line (`// semlf-ignore-next`),
  a directive-only HTML comment line in Markdown (`<!-- semlf-ignore-next -->`),
  a single-line block comment (`/* semlf-ignore-next */`),
  and a docstring or Markdown prose line that is nothing but the directive —
  the bare form exists because a docstring has no comment syntax of its own.
- **Trailing**: a raw prose or comment line ending with a comment leader immediately followed by one directive.
  The leader is the file's line-comment marker,
  or `<!--` with its matching `-->` in Markdown:
  `A long judged line. <!-- semlf-ignore long -->`.
  Inside a line comment the trailing form repeats the marker,
  `# a judged line.  # semlf-ignore`,
  because the directive must sit in a leader-marked tail of its own.
  "Ending with" is exact:
  after the end trim,
  the carrier is the rightmost suffix running from a leader to the end of the line and holding one directive;
  any text after the closing `-->` disqualifies that comment as a carrier,
  and when a line holds two HTML comments,
  only the final one can be the carrier while an earlier one stays prose.

Everything else is literal text.
A token mentioned mid-sentence is prose about the directive, not a directive;
a token inside a code span or fenced block is example text;
neither suppresses anything.
Two residual captures remain, and both are accepted and stated here:
a prose line consisting of nothing but a well-formed directive,
and prose whose final suffix is exactly a trailing carrier —
each is read as a directive even in a document that meant to display it.
The escape for both is the code span or fence a document displaying syntax uses anyway.

Contexts the extractor already excludes from the prose stream are never carriers,
and a token inside them is wholly inert, **including its `-next` effect**:
fenced and indented code, frontmatter, tables, `<pre>` blocks,
reference definitions, string literals in code,
paragraphs removed by the licence cut,
and files skipped by their generated marker where the core applies one.
A closing fence, a licence footer, or generated output can therefore never reach past its own context,
and none of them can suppress real prose after it.
The directive-only HTML comment is the one markup line the stream keeps:
the extractor yields it as a candidate instead of dropping it,
and what it suppresses is read only after the licence cut has filtered the stream.
Identification and recognition are therefore two steps, in that order,
and a candidate inside a removed paragraph is never read as a directive at all.
The candidate row sits in its paragraph for that cut,
so a licence marker can silence a slightly wider paragraph than it would have —
a stated missed-finding trade, never a false positive.

### What a suppression matches

A diagnostic is suppressed when its **anchor** line is the directive's target line.
`wrap` anchors on the upper line of its boundary,
so the directive stands on (or `-next`-points at) the line the report names —
the same line a reader would look at.
`semlf-ignore-next` targets exactly the next raw line, never skipping blanks;
when that line carries no findings, the directive does nothing.
When a line is targeted twice —
its own `semlf-ignore` and a `semlf-ignore-next` from the line above —
the suppressed kinds are the union of the two argument lists.
Ownership and evidence play no role in matching:
they answer "did an edit cause this?",
suppression answers "the author has judged this line and said leave it alone",
and the two questions stay independent.

### Interaction with changed spans

Suppression is applied **after** the ownership filter,
and is independent of spans entirely:
a suppressed diagnostic stays suppressed whether the line was just edited or not,
and an edit near a suppressed line never resurrects it.
Under ADR-0005's model the pipeline is detect → filter by ownership → drop suppressed → report.

### A standalone directive is a paragraph boundary

A standalone directive line is not prose;
it leaves the stream the way build directives do,
so the directive line itself can never carry a finding,
and **no `wrap` is detected across it**.
One consequence is normative:
a standalone directive inserted *between* the two lines of a wrap boundary does not suppress that wrap —
it dissolves the wrap instead,
because the two lines no longer sit in one paragraph.
No finding survives either way and no false positive is created,
but the placements this contract supports are the ones that suppress rather than dissolve:
a trailing directive on the upper line,
or `semlf-ignore-next` on the line above the upper line.
A trailing directive changes nothing about the paragraph;
its line stays prose and is still checked for every kind it does not suppress.
What the predicates see is the judged prose, not the suppression syntax:
a recognized trailing carrier is removed from the analyzed text before any predicate runs,
while the original raw line remains the source for anchors and locations.
`long` measures the judged prefix rather than the raw line with its carrier,
so the directive's own characters never create or mask a finding —
suppression stays a reporting filter,
never an input mutation with cross-kind effects.

### Who writes one

Suppression is explicit, locally scoped, and user-directed.
**An agent never adds a suppression directive on its own authority.**
Repeated hook feedback neither creates a suppression nor authorizes another rewrite attempt;
the bounded-disagreement path (the judgment layer)
surfaces the disagreement to the user,
and the user decides whether the answer is a rewrite, a suppression, or nothing.

This instruction lands verbatim on every judgment-layer surface,
and for it this ADR is authoritative over ADR-0006 and ADR-0007,
which predate the suppression contract.
The surfaces, each named with the plan that owns it:

- the hook feedback text — Plan B, the release where suppression ships;
- the Claude Code skill, the Codex native `SKILL.md`,
  and the `SNIPPET.md` fallback — Plan C, which installs the judgment layer everywhere.

### When it ships

With context-aware hooks, in the same change, never after them —
the roadmap's standing constraint,
because widening what the hook can see without an escape hatch is what makes users disable a guardrail.
The syntax freezes at v1.0 with the other stable contracts.

## Rejected

- **Block form (`semlf-off` / `semlf-on`).**
  Every block system needs an answer for the unclosed `off`,
  and every answer is bad:
  silently suppressing to end-of-file hides real findings,
  erroring on it blocks edits over prose bookkeeping,
  and auto-closing at paragraph end makes scope depend on blank lines.
  The stateless form deletes the whole question.
- **Recognizing the token anywhere in a raw line.**
  The first draft did this,
  which let prose that merely discusses `semlf-ignore` suppress its own findings,
  and let a token on a closing fence reach past the fence through `-next`.
  Recognition scoped to the two carrier forms keeps every capture intentional.
- **A file-level switch.**
  Turning a file off belongs to configuration and `skip_path`,
  which v0.6's project config owns;
  a suppression comment that governs text far from itself is not locally scoped.
- **Fingerprint or hash-based suppression.**
  Tracking a finding across edits by content hash is machinery this tool's precision level does not earn;
  a line-scoped comment is inspectable in review diffs, a hash is not.
- **Partially honoring a malformed argument list.**
  Stated above: a typo should disable the directive visibly, not half-work.

## Non-decisions

- Whether malformed or unused directives are surfaced by a doctor-style command is left to v0.6,
  where `doctor` lands.
- Carrying suppressed diagnostics in `--json` under a flag, instead of dropping them,
  is left to the release that first needs it;
  this contract only fixes that default reporting drops them.
