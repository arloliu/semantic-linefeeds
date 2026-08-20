# Detector Implementation Specification

**Status:** living implementation specification
**Applies to:** `scripts/check_linefeeds.py` version 0.8.1 at the current repository head

## Purpose and authority

This document describes the behavior implemented by `scripts/check_linefeeds.py`.
It covers extraction, detection, suppression, changed-span ownership, and configuration.
It also covers hook delivery and file-mode output.

The source and tests remain authoritative when this document and the implementation disagree.
A detector change that alters behavior described here must update this document in the same change.

The detector follows two policy constraints:

- It prefers precision over recall for `fused` and `wrap`.
- It treats `long` as a length-only advisory that always reports prose beyond the active threshold.

The detector does not decide how to repair prose.
It reports candidates for an agent or person to judge.

## Public entry points

The portable core exposes these entry points:

| Entry point | Contract |
|---|---|
| `diagnose(text, path, spans=None)` | Returns rich diagnostic dictionaries for one after-state text snapshot. |
| `check(text, path)` | Projects each rich diagnostic to `(line, kind, message, excerpt)`. |
| `to_schema(path, diagnostics)` | Wraps one file's diagnostics in JSON schema version 2. |
| `run_sources(sources, as_json=False)` | Checks supplied `(path, text)` pairs with file-mode rendering and status. |
| `run_files(paths, as_json=False)` | Reads named files, then delegates to `run_sources`. |
| `run_hook_claude()` | Reads a Claude-shaped post-tool payload from standard input. |
| `run_hook_codex()` | Reads a Codex `apply_patch` payload from standard input. |
| `main()` | Implements the standalone `--file` and `--hook` command line. |

`diagnose` is the behavioral center.
Every adapter eventually supplies text and a path to it.

## Target files

Markdown dispatch is case-sensitive and recognizes `.md`, `.markdown`, and `.mdx`.
Code dispatch is also case-sensitive.

| Language profile | Extensions | Line comment | Doc line | Block comment | Python-style docstrings |
|---|---|---|---|---|---|
| Go | `.go` | `//` | none | `/* ... */` | no |
| C family | `.c`, `.h`, `.cc`, `.cpp`, `.hpp`, `.hh`, `.java`, `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.cs`, `.kt`, `.kts`, `.swift`, `.scala`, `.dart`, `.m`, `.mm`, `.php`, `.groovy`, `.gradle` | `//` | `///` | `/* ... */` | no |
| Rust | `.rs` | `//` | `///`, `//!` | `/* ... */` | no |
| Python | `.py`, `.pyi` | `#` | none | none | yes |
| Shell | `.sh`, `.bash` | `#` | none | none | no |
| VB.NET | `.vb` | `'` | `'''` | none | no |
| SQL | `.sql` | `--` | none | `/* ... */` | no |
| Lua | `.lua` | `--` | none | `--[[ ... ]]` | no |
| Ruby | `.rb`, `.rake` | `#` | none | none | no |
| Perl | `.pl`, `.pm` | `#` | none | none | no |
| PowerShell | `.ps1`, `.psm1`, `.psd1` | `#` | none | `<# ... #>` | no |
| R | `.r`, `.R` | `#` | `#'` | none | no |
| Haskell | `.hs` | `--` | none | `{- ... -}` | no |
| Elixir | `.ex`, `.exs` | `#` | none | none | no |
| Zig | `.zig` | `//` | `///`, `//!` | none | no |

An unsupported path produces no diagnostics.
`diagnose` still validates supplied spans before it checks whether the path is supported.

## Discovery filters

Hook mode skips a path when any normalized path component is one of:

`vendor`, `node_modules`, `testdata`, `fixtures`, `.git`, `dist`, `build`, or `tmp`.

Hook mode also skips paths below the platform temporary directory and paths excluded by project configuration.
These filters govern discovery only.
An explicitly named `--file` path is always checked.

Temporary-directory lookup failure disables only that filter.
The hook continues instead of rejecting an edit.

## Project configuration

### Discovery

Configuration lives in one `.semlf.ini` file.
Discovery starts from the nearest existing ancestor directory of the target path.
It resolves that directory through symlinks once, then walks physical parent directories.

The walk stops at the first directory that contains `.semlf.ini` or a `.git` entry.
When both exist in the same directory, `.semlf.ini` applies.
Configuration does not cross that repository boundary.

Unreadable, undecodable, or syntactically invalid files contribute no configuration.
`DEFAULT` values never inherit into `[semlf]`.
An invalid individual value drops only its own key.

### Keys

The `[semlf]` section accepts:

| Key | Parsed value | Invalid-value behavior |
|---|---|---|
| `long-limit` | Non-negative decimal integer | Drop this key. |
| `exclude` | One normalized pattern per non-empty line | Drop the key when no pattern remains. |
| `experimental-wrap` | A `ConfigParser` boolean | Drop this key. |

Unknown keys have no effect.

### Long-limit precedence

The long-line threshold resolves in this order:

1. The process-global value set by `--long-limit`.
2. A non-negative integer in `SEMLF_LONG_LINE`.
3. The discovered `long-limit` value.
4. The built-in default of 120 Unicode code points.

A malformed or negative environment value falls through to the next source.
Zero disables `long` diagnostics.
Configuration is loaded on every resolution and is not cached.

### Experimental-wrap precedence

`SEMLF_EXPERIMENTAL_WRAP` decides outright when it contains a non-empty value.
After trimming and lowercasing, `0`, `false`, `no`, `off`, and whitespace-only content mean disabled.
Any other non-empty value means enabled.

An unset or empty environment value falls through to `experimental-wrap` in `.semlf.ini`.
The default is disabled.

### Exclude grammar

Exclude matching uses `/`-normalized, config-root-relative paths and case-sensitive segment matching.
`*` and `?` never cross a path separator.

- A trailing-slash pattern names directories.
- A trailing-slash pattern with an internal slash anchors its segment chain at the config root.
- A trailing-slash pattern without an internal slash matches a directory name at any depth.
- A non-trailing pattern with an internal slash must match the whole relative path.
- A non-trailing pattern without an internal slash may match any one path component.

Paths outside the configuration root and cross-drive paths fail open and remain included.
Paths whose relative form cannot be computed do the same.

## Prose stream model

Both extractors yield `(line_number, raw_line, prose)` triples.
A triple whose `prose` is `None` creates a paragraph boundary.
`wrap` compares only adjacent prose triples within the same paragraph.

Extraction uses `str.splitlines()`.
LF, CRLF, bare CR, and Python-recognized Unicode line separators therefore share the same line-number model.

### Common non-prose rules

After comment markers have been removed, a line is non-prose when it is empty or meets any of these tests:

- It contains `://` anywhere.
- It begins with `#`, `|`, `>`, `<`, `@`, or `\`.
- It begins with a PowerShell help keyword such as `.SYNOPSIS` or `.PARAMETER`.
- It contains only braces, parentheses, brackets, semicolons, commas, or whitespace.
- It consists of three or more repetitions of one non-word punctuation character.

These are whole-line exemptions.
For example, a prose line containing a URL is not partially analyzed around the URL.

### Markdown extraction

Markdown applies these rules in source order:

1. Remove every leading blockquote marker while preserving indentation inside the quote.
2. Treat a first-line `---` as frontmatter and skip through the next `---` line.
3. Skip the body of an active `<pre>` block through the line containing `</pre`.
4. Detect a table when a pipe-bearing line is followed by a pipe-bearing delimiter row.
5. Skip table lines until a blank, heading, backtick fence, or tilde fence ends the table state.
6. Open a fence on at least three backticks or tildes.
7. Close a fence only with the same character and at least the opening width.
8. Skip four-space-indented and tab-indented code.
9. Skip Markdown link reference definitions, their bare destinations, and their title lines.
10. Preserve a well-formed directive-only HTML comment as a suppression candidate.
11. Skip blank lines, headings, pipe-led lines, URL-bearing lines, and inline-HTML-led lines.
12. Emit a paragraph boundary before each new list item, remove its marker, and emit the remaining prose.

An ordinary or malformed standalone HTML comment remains markup and creates a paragraph boundary.
A list continuation without a new list marker remains in the preceding item's paragraph.

### Code extraction

The code extractor recognizes full-line comment surfaces.
It does not parse a language grammar or syntax tree.

- A block comment opens only when the stripped raw line starts with its opening delimiter.
- A line comment is recognized only when the stripped raw line starts with a configured marker.
- Inline comments that follow code are not extracted.
- Consecutive line comments coalesce only when their raw indentation columns match.
- Entering or leaving a block comment creates a paragraph boundary.
- A change in line-comment indentation creates a paragraph boundary.

Within doc comments and docstrings, doctest regions begin with `>>>` and run through the next blank line.
Backtick and tilde fences toggle a scoped fence state.
`<pre>` blocks and content indented four spaces or one tab are also skipped.
All of these states reset when their containing comment or docstring scope ends.

Configured compiler, linter, build, and documentation directives create paragraph boundaries.
The exact patterns vary by language.
They include shebangs, Go build directives, Python checker directives, and JavaScript lint directives.
They also include Ruby magic comments, Lua annotation lines, and PowerShell region or requirement lines.

| Profile | Directive patterns after trimming the raw line |
|---|---|
| Go | Unspaced `//name:`, `// +build`, and `// gofail:` forms. |
| C family | Unspaced `//name:` plus `eslint`, `prettier`, `biome`, `@ts-`, `tslint`, `NOLINT`, `noinspection`, `istanbul`. |
| Python | Shebang, Emacs `-*-` cookie, `noqa`, `type:`, `pylint:`, `ruff:`, `flake8:`, `fmt:`, `isort:`, `mypy:`, `pragma:`, and unspaced `#name:` forms. |
| Shell | Shebang and `shellcheck`. |
| Lua | `---@`. |
| Ruby | Shebang, `frozen_string_literal`, `rubocop`, `encoding`, and `typed` magic comments. |
| Perl | Shebang. |
| PowerShell | Shebang, `#Requires` or `#requires`, and case-insensitive `#region` or `#endregion`. |
| R | Shebang. |
| Elixir | Shebang. |

Profiles absent from this table have no configured directive regular expressions.

### Python docstring tracking

Python receives a small state machine rather than a parser.
It recognizes:

- A module docstring at the beginning of the file.
- A docstring immediately after a `def`, `async def`, or `class` signature ending in `:`.
- A signature continued across lines by counting `(` and `)`.
- Triple-single-quoted and triple-double-quoted strings preceded by zero to two characters from `rRuUbB`.

The tracker does not validate whether a two-character prefix is legal Python.

Inside a docstring, content indented at least four columns beyond the opening quote is treated as example code.
One-line docstrings create an immediate scope exit and paragraph break.

The tracker deliberately remains lexical and incomplete.
A comment marker inside a signature default can make it miss the following docstring.

Python also receives standard-library tokenization for non-docstring multiline strings.
Lines occupied by a multiline `STRING` token are recorded before comment extraction.
On Python 3.12 and later,
multiline `FSTRING_MIDDLE` segments provide the same evidence for f-string literal content.
If a marker-led line belongs to one of those tokens,
it cannot enter the prose stream or act as a suppression carrier.
An unfinished triple-quoted string or f-string is protected from the reported start row to end of file.
Other tokenization failures retain any ranges already identified and otherwise preserve the previous fallback behavior.
Recognized docstrings take precedence over this exclusion and remain prose.

Neither line inside this string is read, as prose or as a directive:

```python
value = """
# semlf-ignore-next
# One sentence here. Another sentence follows.
"""
```

An unfinished *statement* is a different case and protects nothing:
tokenization ends there too,
but the reported message distinguishes it from an unfinished string,
so a comment after an unclosed bracket is still checked.

Other language profiles do not yet have equivalent string-literal lexical coverage.
A marker-led line inside one of their multiline strings can still be misread as a real comment.
[ADR-0020](decisions/0020-string-literal-inertness-follows-lexical-coverage.md) fixes the scope of the guarantee:
it follows lexical coverage,
and it is never inferred from delimiter resemblance.

## Generated files and licences

Generated-file filtering applies to code profiles, not Markdown.
Generated-marker matching is case-sensitive.
The detector skips the entire code file when `Code generated`, `@generated`, or `DO NOT EDIT` appears either:

- Anywhere in the first five raw lines.
- Anywhere in consecutive header comments before the first code line.

The first-five-lines check is raw substring matching.
A marker inside code or a string in that window also skips the file.

Licence filtering recognizes SPDX identifiers, common copyright forms, the copyright symbol, and `All rights reserved`, case-insensitively.

For code, the detector removes a leading licence comment region through its computed extent.
It also buffers every later prose paragraph and removes the whole paragraph when any line contains a licence marker.
Markdown uses only the paragraph rule.

A truly blank line ends the leading licence region.
A multi-paragraph licence can therefore leave later paragraphs visible unless each paragraph carries a marker.

## Detection pipeline

`diagnose` performs these stages in order:

1. Normalize every supplied changed span.
2. Select and filter the prose stream.
3. Parse standalone and trailing suppression carriers while walking the stream.
4. Detect every `fused` match on the current prose line.
5. Compare the previous prose line with the current line for `wrap`.
6. Measure the current prose line for `long`.
7. Sort diagnostics by anchor line while preserving same-line insertion order.
8. When spans were supplied, keep only exactly located diagnostics whose ownership touches a span.
9. Remove diagnostics suppressed for their kind and anchor line.

The same-line order is `fused`, then `long`, then `wrap`.
Multiple `fused` matches retain their left-to-right order before the other kinds.

## `fused`

`fused` looks for two sentence-shaped units on one extracted prose line.
It reports every non-overlapping regular-expression match.

The left side must end with:

- An ASCII lowercase word of at least two letters, except `al`, `cf`, `esp`, `viz`, and `vs`.
- Or an inline code span.

That token must be followed by `.`, `!`, or `?`.
Closing quotes, parentheses, brackets, and common emphasis marks may follow the terminator.
At least one whitespace character must follow.

The right side must begin with either:

- An ASCII uppercase letter.
- Or an inline code span followed by a word character in the same sentence.

The diagnostic anchors on the current raw line.
Its evidence is that line.
Its ownership starts at the matched left token and extends through the right opening token.
It then extends through adjacent non-whitespace tail characters on the raw line.

The rule does not recognize sentence boundaries after numbers, one-letter tokens, or uppercase tokens.
It does not recognize them after non-ASCII scripts either.
It also cannot distinguish every abbreviation period from a sentence period.

The exclusion list settles that last limit one entry at a time.
`al` is on it because a citation reaches the rule as ordinary prose:

```text
The Smith et al. Nature paper argues otherwise.
```

`fused` is the only blocking kind,
so the alternative was blocking an edit on a correct line.
The cost is a missed finding wherever `al.` genuinely ends a sentence,
which the precision policy accepts.
The exclusion is anchored at a word boundary,
so a word that merely ends in a listed spelling still reports.

## `wrap`

`wrap` looks for a physical line break that may split one clause.
It reports on the upper line only when all of these conditions hold:

1. The two lines are consecutive prose lines in the same extracted paragraph.
2. The upper line, after trailing-markup peeling, does not end in an accepted line ender.
3. The lower line begins with an ASCII lowercase word.
4. That lower opening word is not in `CONNECTORS`.

Trailing-markup peeling runs in this order:

1. Remove a closing emphasis delimiter when the same delimiter also appears earlier on the line.
2. Remove a trailing single-backtick code span when other prose precedes it.
3. Apply the emphasis rule again when step 2 exposes another closing delimiter.

A line containing only a code span keeps the span.
Prose before the span is what makes the span peelable,
so the upper line here is reported:

```text
Use the value from `Read`
implementation continues here.
```

Accepted line enders include ASCII sentence and clause punctuation.
They include ASCII hyphen variants and common closing quotes or brackets too.
They also include the implemented full-width CJK punctuation set.

The exact character sequence is:

```text
.!?;:,—-–)”"'`。！？；：，、）」』》】’
```

`CONNECTORS` contains:

| Family | Members |
|---|---|
| Coordinating | `and`, `but`, `so`, `or`, `nor`, `yet` |
| Relative | `which`, `that`, `where`, `who`, `whose`, `whom` |
| Subordinating or conditional | `when`, `while`, `because`, `although`, `though`, `unless`, `until`, `if`, `as`, `since`, `once`, `whereas`, `whenever`, `whether` |

`before` and `after` are intentionally absent.
Membership alone cannot separate their prepositional and subordinate-clause uses.

The diagnostic anchor is the upper raw line.
Evidence runs from the start of the upper line through the content of the lower line.
Ownership begins at the upper line's final peeled token.
It crosses the physical boundary and ends after the lower line's opening word.

`wrap` is a closed-world heuristic.
Correct breaks before lowercase phrases outside `CONNECTORS` can produce false positives.
For that reason, hooks withhold it by default and it never blocks.
The one line it still reaches is a line a blocking finding already holds,
where the repair needs it and the withholding protects nothing.

## `long`

`long` reports when the extracted prose length is strictly greater than the active nonzero limit.
It counts Python Unicode code points, not raw columns, bytes, grapheme clusters, or terminal display width.

Indentation and comment markers do not count.
Markdown list markers, quote markers, and recognized trailing suppression carriers do not count either.

`BOUNDARY_HINT_RE` refines the message but never gates the diagnostic.
It recognizes semicolon, colon, em dash, or a spaced en dash.
It also recognizes a comma followed by `and`, `but`, `so`, `which`, `that`, or `where`.
The hint does not prove that a safe clause boundary exists.

`long` anchors on and owns the extracted prose line.
It is always advisory and never changes an exit status by itself.

## Diagnostic ranges and changed spans

Every rich diagnostic contains:

| Field | Meaning |
|---|---|
| `kind` | `fused`, `wrap`, or `long`. |
| `line` | One-based anchor line. |
| `message` | Frozen human-facing explanation. |
| `excerpt` | Extracted prose from the anchor line. |
| `anchor` | Half-open raw anchor-line range without its terminator. |
| `evidence` | Half-open range containing all text examined for the finding. |
| `ownership` | Half-open causal range, or `None` when exact location failed. |
| `ownership_basis` | `token` or `degraded`. |
| `suggestion` | Optional replacement for a narrow `fused` class: `lines` holds the two lines to write, and `replaces` counts the raw lines they replace, starting at `line`. Schema version 2 exists for this field: under version 1 a suggestion always replaced the anchor line alone. |

Offsets count Unicode code points in the supplied text.
A normal span has `start` and `end` offsets.
A deletion boundary uses `at` and normalizes to a zero-width range.
Each form may carry `mapping: exact` or `mapping: degraded`.
The core validates that field but applies the same overlap rule to both values.

Two nonzero half-open ranges touch only when they strictly overlap.
A zero-width range touches another range when its point lies on or within that range, including its edges.

When `spans` is `None`, every diagnostic is eligible.
An empty span list reports nothing.
Under any supplied spans, a diagnostic with degraded ownership is withheld.

## Suppression

Suppression is stateless and line-scoped.
The grammar is case-sensitive:

```text
directive = name (WS+ kind)*
name      = "semlf-ignore-next" | "semlf-ignore"
kind      = "fused" | "wrap" | "long"
WS        = ASCII space or horizontal tab
```

A directive with no kind arguments suppresses all three kinds.
Known kinds may repeat.
One unknown argument makes the entire directive malformed and inert.

`semlf-ignore` targets its own raw line.
`semlf-ignore-next` targets exactly the next raw line and never skips blanks.
Two directives targeting one line union their kind sets.

The extractor recognizes:

- A standalone prose or comment line whose extracted content is exactly one directive.
- A trailing Markdown HTML comment containing exactly one directive.
- A trailing suffix beginning at the rightmost line-comment marker and containing exactly one directive.

Standalone directive lines create paragraph boundaries.
Recognized trailing carriers are removed from both the raw and extracted views before detection.
The judged prefix stays in its paragraph.

Suppression runs after changed-span ownership filtering and matches the diagnostic's anchor line.
A `wrap` suppression must therefore target its upper line.

## Automatic suggestions

Only a `fused` boundary ending in `!` or `?` may carry an automatic two-line suggestion.
The detector withholds the suggestion unless all of these conditions hold:

- The prose contains exactly one `FUSED_RE` match.
- Exactly one ASCII space separates the terminator and the next sentence.
- No closing punctuation or emphasis sits between that terminator and the space.
- The prose contains no backtick, `<`, or `>`.
- The raw line contains the extracted prose exactly once.
- The raw prefix contains only approved whitespace, comment, or blockquote leaders.
- The raw suffix contains only spaces or tabs.
- No trailing suppression carrier was stripped.

When the detector's own `wrap` pairing says the anchor's sentence continues on the line below,
and that `wrap` is not suppressed on the anchor line,
the lower line is inside the repair and the suggestion absorbs it:
the second replacement line carries the split-off sentence rejoined with the lower prose,
one space standing where the anchor's trailing whitespace and terminator were,
and `replaces` is 2.
The absorbed form demands the same safety of the lower line,
each failure named by a `below_` withholding class:

- The anchor's terminator is exactly one LF, and no `\r` sits in the lower raw line.
- The lower prose contains no `FUSED_RE` match.
- The lower prose ends its sentence: terminal punctuation, then only closing delimiters.
- The lower prose contains no backtick, `<`, or `>`.
- The lower raw line contains its prose exactly once.
- The lower leader equals the anchor leader, character for character.
- The lower raw suffix contains only spaces or tabs.
- No trailing suppression carrier came off the lower line.

A paired window that fails any of these carries no suggestion at all:
a one-line split there would repair half the sentence,
which is a wrong repair rather than a smaller right one.
A suppressed `wrap` means the user blessed the break,
so the suggestion falls back to the one-line form with `replaces` 1.

The suggestion duplicates the approved raw prefix onto both replacement lines.
It never edits the file itself.

## Stable snapshots

Hook mapping uses strict UTF-8 reads.
The reader compares device, inode, size, and nanosecond modification time before and after the descriptor read.
It compares the same values against a final path stat.

Any read, decode, in-place mutation, or atomic-replacement mismatch rejects the snapshot.
The caller then uses its payload-only fallback.

File mode differs intentionally.
It decodes with replacement characters and reports only operating-system read failures.

## Claude-shaped hook

The Claude hook accepts any JSON object with a mapping-valued `tool_input` and a supported string `file_path`.
It does not validate `hook_event_name` or `tool_name`.

For `new_string`:

- An empty string is treated as deletion without a locatable preimage and produces no report.
- `replace_all` forces payload-only checking.
- Otherwise, a stable snapshot is read and `new_string` must occur exactly once, including overlapping occurrences.
- A unique occurrence becomes one exact changed span over the full snapshot.
- A missing, ambiguous, unreadable, or unstable snapshot falls back to checking `new_string` alone.

For non-empty `content`, the hook treats the content as a whole-file after-state and one whole-file span.
`new_string` takes precedence when both fields exist.

## Codex hook

The Codex hook requires `tool_name` to equal `apply_patch`.
It reads patch text directly from a string-valued `tool_input`.
For a mapping-valued input, it tries `command`, `input`, then `patch`.

The patch parser recognizes add and update file headers, move destinations, and hunks.
Within hunks, it recognizes added, deleted, and context lines.
Move destinations replace the original path for dispatch and reporting.

For each non-skipped file:

1. Read one stable post-state snapshot.
2. Remove deleted lines from each hunk body.
3. Locate the remaining body as one unique, whole-line-bounded occurrence.
4. Create ranges for added lines and zero-width boundaries for deletion runs.
5. Diagnose the full snapshot under those spans.

If any hunk cannot be mapped, the whole file degrades to payload-only analysis.
The fallback collects maximal contiguous runs of added lines.
Context, deletion, and hunk boundaries end a run.
Runs are joined with blank lines so disjoint additions cannot fabricate a `wrap` boundary.

Degraded reports label line numbers as positions within the added text and add one approximate-position note.
The note appears only when at least one degraded report survives visibility filtering.

## Visibility, rendering, and exit status

File audits see all detected kinds.
Hooks first remove `wrap` unless the active environment or project configuration opts in.

One `wrap` survives that removal without any opt-in:
the one anchored on a line that a blocking finding also holds.
That line is being rewritten whatever the hook says about it,
so the removal has no prose left to protect there,
and the `wrap` is what keeps the repair from stranding the sentence the `fused` split off.
Only a blocking kind corroborates.
A `wrap` beside a `long` on one line is still removed,
because an advisory leaves the line as its author wrote it.

After visibility filtering, delivery follows this matrix:

| Visible result | Hook status | Hook channel | File status |
|---|---:|---|---:|
| No findings | 0 | No output | 0 |
| `long` only | 0 | One JSON object on standard output | 0 |
| `wrap` only, default | 0 | No output | 1 |
| Opted-in `wrap` only | 0 | One JSON object on standard output | 1 |
| Any visible `fused` | 2 | One combined text report on standard error | 1 |
| `fused` and a `wrap` on its line | 2 | Both in that one report on standard error | 1 |
| Read error in `--file` | not applicable | Error on standard error | 1 |
| Usage error | 64 | Usage or error on standard error | 64 |

When one hook delivery contains blocking and advisory findings, standard error carries every visible finding together.
An advisory-only hook report is one JSON object under `hookSpecificOutput.additionalContext`.

A blocking report carrying a withheld finding adds one sentence naming it as direction for the repair,
not as a second repair, and stating that the rejoin comes before the split.

Text excerpts truncate beyond 60 characters.
Every non-empty hook report ends with the bounded-disagreement instruction.
The prohibition on agent-authored suppression follows it as the final text.
The report mentions the judgment skill only when the selected transport can resolve a usable copy.

`--json` is valid only with `--file`.
It emits an array of per-file schema documents and omits clean files.
A clean JSON audit emits `[]`.

## Known limitations

- A sentence genuinely ending in a listed abbreviation goes unreported,
  because `fused` is the blocking kind and a wrong block costs more than a miss.
- `wrap` has known false positives and stays outside default hook feedback by design,
  except on a line a blocking finding already holds.
- A repair that strands an opening on its own line draws only a `wrap`,
  which no block corroborates,
  so a default hook passes that file in silence.
  Delivering the `wrap` beside the block is what prevents the repair, not what catches it.
- `CONNECTORS` can hide genuine wraps because over-inclusion costs recall rather than precision.
- `long` counts code points, so CJK display width and grapheme width are not represented.
- The six-word boundary hint can name list-closing conjunctions that are not clause boundaries,
  but it changes advice rather than eligibility or status.
- The first-five-lines generated marker check can skip a handwritten file.
  The false skip occurs when code or string data contains one of its raw substrings.
- Marker-led multiline-string content can be misread as comments in profiles without lexical coverage.
  Python has coverage for multiline string tokens;
  recognized Python docstrings intentionally remain prose.
- URL-bearing prose lines and licence-bearing paragraphs can contain missed violations.
  Generated files can contain them too,
  because these exclusions operate on whole lines, whole paragraphs, or whole files.
- Payload-only hook fallbacks lose surrounding context and may miss cross-boundary findings.
- Ambiguous token location causes span-scoped diagnostics to be withheld rather than widened to a whole line.
- `--file` returns status 1 for `wrap` even though hooks mostly withhold it, because file mode is an explicit human audit.

These limitations follow the implemented precision and delivery policies.
They should remain explicit so future changes do not mistake a known tradeoff for an accidental regression.
