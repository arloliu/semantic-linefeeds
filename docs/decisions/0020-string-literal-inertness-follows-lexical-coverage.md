# ADR-0020: String-literal inertness follows lexical coverage

**Status:** accepted
**Date:** 2026-08-17
**Amends:** [ADR-0010](0010-suppression-is-a-stateless-single-line-directive.md) —
its string-literal guarantee applies where the extractor identifies the literal lexically,
not to every language profile by assertion alone.

## Context

ADR-0010 says tokens inside code string literals are inert,
including their `semlf-ignore-next` effect.
The suppression engine satisfies that rule for text excluded from the prose stream,
but the code extractor does not parse every supported language.

That distinction was observable in Python.
A marker-led line inside an assigned triple-quoted string entered the prose stream as a comment,
and a directive-shaped line inside the same string could suppress the next marker-led line.
The behavior contradicted the stated contract and could also produce a blocking `fused` false positive.

A universal claim would require reliable lexical scope for every language profile.
Adding a collection of hand-written quote states to the shared extractor would instead create several partial parsers,
each with language-specific escape, raw-string, interpolation, and delimiter rules.
That would widen the false-positive surface the project is designed to minimize.

## Decision

String-literal content is inert when the extractor has lexical evidence that the line belongs to a string.
The contract is limited to that implemented coverage.

For Python,
the core uses the standard-library `tokenize` module to collect lines occupied by multiline `STRING` tokens.
On Python 3.12 and later,
multiline `FSTRING_MIDDLE` segments supply equivalent evidence for f-string literal content.
A comment marker on one of those lines cannot enter the prose stream and cannot become a suppression carrier.
An unfinished triple-quoted string or f-string is protected from its reported start row through the end of the file.
Other tokenizer failures retain any completed string ranges and otherwise fall back to the existing extraction behavior.

Recognized Python docstrings remain prose.
The existing module, function, and class docstring state machine runs before string-line exclusion,
so this decision does not silence documentation.

Profiles without equivalent lexical coverage make no blanket string-literal guarantee.
A marker-led line inside a multiline string in one of those languages remains a known extraction limitation.
Future coverage needs a language-appropriate lexical signal and causal tests;
it must not be inferred from delimiter resemblance alone.

## Consequences

- Python assigned multiline strings no longer produce comment findings or suppression effects.
- Python docstrings keep their existing findings and suppression semantics.
- The core remains one Python 3.9-compatible, standard-library-only file.
- Invalid Python with an unfinished multiline string fails toward silence for that string region.
- Documentation must describe literal inertness as a property of lexical coverage,
  not as a universal property of every configured language.
- Non-Python language profiles can still miss this boundary until they gain equivalent lexical evidence.

## Rejected alternatives

**Keep the broad guarantee and treat the implementation as temporarily incomplete.**
Rejected because an accepted contract must describe behavior users can rely on now.

**Track triple quotes with a regular-expression state machine.**
Rejected because prefixes, escapes, adjacent strings, and invalid input complicate delimiter matching.
Python's tokenizer supplies stronger evidence.

**Build string states for every language in this change.**
Rejected because the profiles do not share one literal grammar,
and a broad pseudo-lexer would trade a bounded known miss for new false positives across the whole detector.
