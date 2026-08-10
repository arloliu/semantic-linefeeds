# ADR-0006: Every agent gets the judgment layer

**Status:** accepted  
**Date:** 2026-08-10

## Decision

The three-layer design is installed only for Claude Code today.
The Codex installer adds the hook and nothing else (`scripts/install.py:69-108`),
its guide leaves the 12-line snippet an optional step (`adapters/codex/INSTALL.md:20-24`),
and the opencode skill must be copied by hand (`adapters/opencode/INSTALL.md:11-20`).
Meanwhile the hook tells every agent to load a skill (`scripts/check_linefeeds.py:582`).

Codex CLI resolves standalone `SKILL.md` skills from a repository `.agents/skills` directory
and from `$HOME/.agents/skills`;
the user-level directory exists and is populated on this machine,
though only the directory convention was verified locally, not the end-to-end load.

- The Codex installer **installs the native skill**, and covers status, upgrade, and uninstall for it.
- `SNIPPET.md` gains the compound-object `and` test, the clause-boundary definition,
  and the never-break list, and remains the fallback for agents that genuinely have no skill mechanism.
- Hook feedback names a judgment layer only when the installer actually supplied one.
- Hook feedback carries a **suggested diff** rather than only a description,
  since agents act on concrete replacements more reliably than on prose instructions.
  This shares its mechanism with the fix delivery in ADR-0007.
