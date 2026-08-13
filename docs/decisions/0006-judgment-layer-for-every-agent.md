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

## Amendment (2026-08-13)

"The installer actually supplied one" is refined to a presence contract:
hook feedback names the judgment layer when a usable skill is **present** at a location
Codex resolves standalone skills from — a repository `.agents/skills` directory,
or `$HOME/.agents/skills` — not when the installer's own provenance is tracked.
The installer is the supported way to put a skill there,
and remains the only place this repository writes one,
but the hook itself checks presence, not provenance.
Provenance tracking arrives with v0.6's installed-digest manifest;
the hint can require it once that manifest exists.
Native-skill removal is deferred the same way:
v0.6's `uninstall` command owns skill removal for every installed adapter,
so this release's Codex installer covers install, status, and idempotent upgrade only.
