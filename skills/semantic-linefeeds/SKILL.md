---
name: semantic-linefeeds
description: Use when writing or editing code comments, doc comments (godoc, javadoc, JSDoc, rustdoc, docstrings), or Markdown prose (README, CHANGELOG, docs, specs, rule files), and when a linefeeds hook reports fused, wrap, or long findings on text just written.
---

# Semantic Linefeeds

Break lines by meaning, not by column.
A line ends where a thought ends:
one sentence per line,
and a long sentence splits only at a real clause boundary.
Column-wrapped prose reflows the whole paragraph when one clause changes;
semantic linefeeds keep the diff to the line that actually changed.

Do NOT imitate the wrapping of surrounding legacy text.
Much existing godoc is column-wrapped at ~80 characters;
that style predates this rule and is exactly what to avoid.

## Phase 1 — while drafting

Hold only one habit while writing: **start a new line after every sentence** (`.`, `!`, `?`).
Do not police line length while drafting — that is Phase 2's job, and doing both at once fails.

## Phase 2 — mechanical check (run after writing any prose block)

Run the checker on every file whose prose you touched:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" --file <files>
```

(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at `../../scripts/check_linefeeds.py` relative to this SKILL.md.)

Then judge each finding — the checker flags suspicion, it does not decide:

- **fused** — split the line after the terminal punctuation.
  This one is almost always correct to fix.
  Before you split, read the line below.
  If the text after the stop does not finish its sentence and the next line opens on a lowercase word,
  the sentence continues there:
  join that text to the line below instead of leaving it standing alone.
  A line holding no whole thought reads worse than the column wrap you started from.
- **wrap** — rejoin the severed clause onto one line, then re-split at sentence ends.
  The repair is confined to the two lines the finding spans;
  if a correct re-split would push text into a third line you did not write,
  rejoin those two lines only and surface the rest under Bounded disagreement.
- **long** — scan rightward from the limit (default 120) for the first clause boundary; break there.
  Nothing rightward: scan backward from that point and break at the last boundary found.
  Nothing in either direction: leave the line long — an over-long line beats a severed clause.

When one line draws both `fused` and `wrap`, rejoin before you split.
Splitting first strands the opening the rejoin was going to absorb,
and the checker then reports the `wrap` you created instead of the one you were given.

A clause boundary is `;`, `:`, `—`, a coordinating conjunction (`and`, `but`, `so`),
or a word opening a subordinate clause —
a relative pronoun (`which`, `that`, `where`) or a subordinator (`because`, `although`, `whereas`).
The words in parentheses illustrate each class rather than exhausting it:
judge the word by whether a clause opens on it, not by whether it appears here.
`and`/`but`/`so` qualify **only when both sides could stand alone as a complete sentence** —
its own subject, its own verb.
Not boundaries: a comma between list items, the `and` that closes a list ("A, B, and C"),
or an `and` joining a compound subject or object ("depends on X and Y").
Check every `and` against this test before breaking at it.

Break placement: punctuation stays at the end of the upper line;
a conjunction or relative pronoun starts the lower line.

## Never break

URLs, compiler and lint directives (`//go:generate`, `//nolint:...`), generated-file headers,
code inside indented godoc examples, and table rows — whatever their length.
Breaking a directive silently stops it from applying.
Also never break: javadoc/JSDoc/doxygen tag lines (`@param`, `\param`);
license headers;
fenced code and `<pre>` blocks inside doc comments;
doctest lines;
and Markdown link reference definitions.

The checker analyzes English prose only.
The two sentence-reading kinds never fire on CJK text:
a CJK paragraph draws no `fused` and no `wrap` however it is broken,
so a clean run over one is silence rather than approval —
apply the one-thought-per-line rule from your own judgment there.
Two exceptions are worth knowing.
A `wrap` can land on a CJK line when an English line follows it,
because that judgment is read off the English line rather than off the CJK text.
A CJK line past the limit draws the `long` advisory like any other,
because that kind counts characters and does not read the sentence;
judge where a CJK line breaks yourself, and leave it long if it has no boundary.

## Scope discipline

Fix only the block you wrote or edited.
Never rewrap stable text elsewhere in the file —
a whitespace-only reflow of untouched paragraphs makes the diff unreviewable.
A whole-file reflow happens only when the user asks for one by name, in its own commit.

## Bounded disagreement

Judge a finding before rewriting.
A finding you believe is a false positive, or one that survives one repair attempt, ends the loop:
stop retrying and surface the disagreement to the user instead of rewriting correct prose again.
An agent never adds a suppression directive on its own authority: if you judge a finding to be a false positive, leave the text as it is and surface the disagreement to the user instead.
Never add a `semlf-ignore` or `semlf-ignore-next` directive on your own authority —
see the [suppression section](../../README.md#suppressing-a-finding) for who writes one.

## Common mistakes

| Mistake | Fix |
|---|---|
| Wrapping at ~75–80 chars like gofmt-era godoc | That is the training prior, not the rule; sentence ends decide breaks |
| Copying the column-wrapped style of legacy text in the same file | New prose follows this rule regardless of neighbors |
| Breaking at an `and` that joins a compound object | Both sides must stand alone as sentences; rejoin if not |
| Wrapping defensively to satisfy a linter | No linter checks line length; never wrap for a tool |
| Skipping Phase 2 because the draft "looks right" | Length judgment fails during drafting; always run the checker |
