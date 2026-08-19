# ADR-0025: A line split out of a list item carries a continuation, not a second marker

**Status:** accepted
**Date:** 2026-08-19
**Amends:** [ADR-0023](0023-what-a-repair-corpus-measures.md) —
its normalization section says a repair's leaders are judged by the detector's own walk,
and the rule that walk was judged against repeated every leader byte for byte.
That rule cannot express the correct repair for a list item.

## Context

The repair corpus generates candidate repairs mechanically
and asks three model families which of them are correct.
The generator built each produced line by repeating,
byte for byte, the leader of the window line its text came from.

For a blockquote, a comment marker, and an indent that is right.
For a list marker it is wrong, and obviously so:

```markdown
4. Having the GODEBUG settings is not enough. Developers need to be able to determine
   which ones to use when updating to a new Go toolchain.
```

Splitting the anchor at the sentence boundary has one correct answer:

```markdown
4. Having the GODEBUG settings is not enough.
   Developers need to be able to determine which ones to use when updating.
```

The generator produced `4. ` on both lines, which is two list items rather than one,
and the candidate failed its own validation.
So the acceptable set for that window could hold nothing but the original.

**Two of the three model families found this on the first batch each of them saw.**
Both reported the correct repair as one the generator never offered.
That is the signal the corpus already treats as an instrument defect rather than an answer.

Measured over the drawn round, **57 of 308 judgeable units had no expressible split**.
That is 19%, every one of them a list-marker unit,
and one whole reportable stratum was affected end to end.
A round spending a fifth of its elicitation on that finding measures the generator.
It does not measure the agents.

## Decision

**A second or later line split out of a list item carries a continuation.**
The first line keeps the marker.
Every line after it carries the continuation instead.

**The continuation is the one the window itself shows.**
Markdown accepts two forms —
an indent under the marker, or no indent at all, which it continues lazily —
and the file being repaired has already chosen between them.
Where a window's lower line is a continuation of the same item, its leader is copied.
Where it is not, the fallback is an indent of the marker's own width,
every non-whitespace character of the marker replaced by a space.

Copying the file's answer is what keeps this from being a style choice made here.
Both forms occur in the drawn population:
14 of 24 two-line list windows indent, and 10 continue lazily.

**A lower line that opens its own marker is a sibling, not a continuation,
and is not copied from.**
The extractor already separates two list items into two paragraphs,
so no window spans them today;
the rule says what it would do anyway.
A leader copied from a sibling would open a third item.

**Nothing else changes.**
A blockquote marker, a comment marker, and an indent still repeat byte for byte.
The rule is narrower than "leaders may be rewritten":
it names one construct, and the construct's own file supplies the answer.

## Consequences

The three list-marker strata become scoreable.
The generator now offers a valid split for 80 of the round's list-marker units
where it previously offered one for 23.

Every acceptable-set decision made before this change is void,
so the round is redrawn.
Nothing had been collected, which is why this cost a redraw and not a round.

## Alternatives rejected

**Leave it, and record that list items cannot be scored.**
Three of the ten reportable strata are list-marker strata,
and 19% of the round's elicitation would have gone to producing an instrument finding.
Refusing to measure a construct is worth recording only when the limit is real.
This one was a defect.

**Drop list-marker units from the draw.**
Cheaper, and it decides by exclusion that list items are out of scope for a widening.
That is a scope call, and nothing in this project's records had made it.

**Choose one continuation form and always emit it.**
Both forms are correct Markdown and files use both.
Choosing here would put a style judgment into the instrument,
which is what the generator exists not to do.
