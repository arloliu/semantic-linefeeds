## Semantic linefeeds

When writing or editing prose in code comments, doc comments, docstrings, or Markdown:
break lines by meaning, not by column.
One sentence per line;
a sentence longer than the configured limit (default 120 chars) splits only at a real clause boundary
(`;`, `:`, `—`, or a conjunction where both sides stand alone).

A conjunction (`and`, `but`, `so`) or relative pronoun (`which`, `that`, `where`) is a boundary only when both sides could stand alone as a complete sentence.
A compound subject or object does not split:
"depends on X and Y" has no boundary at "and".

Never break: URLs; compiler and lint directives; generated-file headers;
javadoc/JSDoc/doxygen tag lines; license headers; fenced code and `<pre>` blocks;
doctest lines; Markdown link reference definitions; and table rows.
Never rewrap existing text you are not otherwise editing.

Judge a finding before rewriting.
A believed false positive, or a finding that survives one repair attempt, ends the loop:
stop retrying and surface the disagreement to the user instead of rewriting correct prose again.
An agent never adds a suppression directive on its own authority: if you judge a finding to be a false positive, leave the text as it is and surface the disagreement to the user instead.

Check your work with:

    semlf --file <files you touched>

(If `semlf` is not installed:
`uv tool install semlf`, or the equivalent `pipx install semlf`.)
