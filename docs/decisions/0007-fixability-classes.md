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
