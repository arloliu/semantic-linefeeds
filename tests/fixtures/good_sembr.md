# Worker pool

The pool starts one worker per configured slot and hands each submission to the first idle worker.
A submission that arrives while every worker is busy blocks until a slot frees.

Column-wrapped text inside a code fence must never be flagged, so this block stays silent:

```text
The pool starts one worker per configured slot and hands each submission to
the first idle worker. A submission that arrives while every worker is busy
blocks until a slot frees.
```

Semantic breaks may end a line at a comma,
and the next line may open with a conjunction.
A break may also land before a relative clause,
which starts the lower line without triggering the wrap check.

- A list item is one sentence on one line, and the comma before this `and` is a list-style pause.
- Another item follows it.

| Column A | Column B with a long wrapped-looking cell that would otherwise trip the checks entirely |
| -------- | --------------------------------------------------------------------------------------- |
| a        | b                                                                                        |

See <https://example.com/a/very/long/url/that/should/never/be/broken/or/flagged/by/any/of/the/three/heuristics/at/all> for details.
