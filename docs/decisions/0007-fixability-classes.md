# ADR-0007: Automatic repair is restricted to `!` and `?`

**Status:** accepted  
**Date:** 2026-08-10

## Decision

`fused` misfires on abbreviations, so a period boundary cannot be proven safe by an allowlist,
which is open by construction.
Three entries proposed earlier — `Fig.`, `No.`, `Eq.` —
cannot match the current case-sensitive regex at all (`scripts/check_linefeeds.py:75-78`).

- Period-based `fused` stays a **suggestion**.
- The first automatic class is restricted to `!` and `?`, after protected-span checks.
- Any fix reconstructs raw source, preserving markers, indentation, block prefixes, quoting,
  and newline style, and is byte-identical outside the replacement.
- A content hash is compared immediately before writing.
- **Preferred delivery is an exact replacement handed back for the agent's next edit.**
  Hook-side mutation stays deferred until adapters can force a file-view refresh.

## Amendment (2026-08-13)

The newline-style and content-hash clauses above bind any path that **writes** the file —
the still-deferred hook-side mutation.
A delivered suggestion is not that path:
it is a two-line replacement handed back as display text in hook feedback,
whose insertion point and inserted text are exact —
one line break, replacing the single inter-sentence space,
plus the source line's own prefix repeated onto the second line, and nothing else.
Nothing in the delivery path reads or writes a byte of the file itself.
