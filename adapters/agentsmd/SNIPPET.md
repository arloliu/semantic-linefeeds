## Semantic linefeeds

When writing or editing prose in code comments, doc comments, docstrings, or Markdown:
break lines by meaning, not by column.
One sentence per line;
a sentence longer than ~120 characters splits only at a real clause boundary
(`;`, `:`, `—`, or a conjunction where both sides stand alone).
Never break URLs, compiler/lint directives, example code, or table rows.
Never rewrap existing text you are not otherwise editing.
Check your work with:

    python3 <repo>/scripts/check_linefeeds.py --file <files you touched>
