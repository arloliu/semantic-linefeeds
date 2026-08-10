# ADR-0005: Analysis sees the file; reporting follows ownership

**Status:** accepted  
**Date:** 2026-08-10

## Decision

Unifying the three entry points on `check(full_text, path, changed_spans)`
gives context-awareness, real Codex line numbers, and one contract for the git modes.

### Three ranges, not two

v2 used anchor plus evidence and reported on evidence intersection.
That alone does not preserve the invariant:
an unchanged candidate boundary can be reported once a newly edited sentence becomes its supporting evidence,
even though the accused line break itself never changed.

Every diagnostic therefore carries:

- an **anchor range** — where it is displayed;
- an **evidence range** — all context used to establish it;
- an **ownership range** — the accused physical boundary itself.

Ownership by kind:

| Kind | Ownership range |
|---|---|
| `wrap` | the upper line's terminal token, the newline boundary, and the lower-line opening token |
| `fused` | the complete regex match, through the right-hand opening token |
| `long` | the changed prose line |

Ownership covers **local causal text**, not only the physical separator.
For `fused`, lowercasing to uppercase on the right-hand side can create a match
that punctuation-only ownership never sees (`scripts/check_linefeeds.py:75-78`),
so ownership runs through the right-hand opening token.
For `wrap`, no ownership exists in **default hook output**, since no `wrap` reaches it.
The retained predicate still produces findings in `--file` audits and in opt-in evaluation,
so those modes use the range in the table above,
and any replacement predicate must redefine ownership when it is introduced.
Width never appears in ownership, since ADR-0002 leaves it qualifying nothing.

**A diagnostic is reported only when its ownership range intersects a changed span or boundary.**
Preimage comparison is a second condition, never a substitute.
Ranges are defined over Unicode code points,
with explicit rules for zero-width intersection and discontiguous evidence.

### Span sources

| Source | Rule |
|---|---|
| Edit, `new_string` found once | Map to that span |
| Edit, found zero or several times | Payload-only fallback |
| `replace_all: true` | Spans only from a preimage or a tool-supplied diff |
| Write | `content` is both context and a whole-file span |
| Codex patch | Match full hunk context against a stable post-state; else addition-run fallback |
| `--staged` | The index blob, never the worktree |

Changed spans are half-open after-state ranges plus zero-width boundaries,
because deleting a newline can create a `fused` violation no added-line range represents.
Every span records whether its mapping is exact or degraded.
The core reads one stable snapshot and detects modification during the read;
on any mismatch or degraded mapping it falls back to payload-only checking.
**The existing snippet mode is retained as that fallback, not deleted.**

`.agents/rules/100-project-map.md:27-34` is amended in the same change,
restated as: analysis may see the whole file;
reporting is restricted to diagnostics **owned** by a change.
