# Semantic-Linefeeds — Agent Rules Index

Trigger map for repository rules.
Read `000-agent-contract.md` for every task,
then the files whose triggers match the work.
If in doubt, read the file rather than guess its contents.

## Default Load

- Most implementation tasks: `000`, `100`.
- Add `300` for test or fixture changes.
- Add `600` for commits, branches, or PRs.
- Tiny doc-only edits: `000` plus the self-hosting rule in the root `AGENTS.md` is enough.

## Always

- **[000-agent-contract.md](000-agent-contract.md)** —
  don't guess, keep changes small, surface conflicts, fail loud,
  and write all prose with semantic linefeeds.

## Before Code Changes

- **[100-project-map.md](100-project-map.md)** —
  file layout, the single-file stdlib-only core, adapter contracts,
  and the invariants (precision over recall, exit codes, hook scope).

## Before Adding/Changing Tests or Fixtures

- **[300-testing.md](300-testing.md)** —
  inline-marker fixtures, extraction goldens, payload replays,
  the bun suite, and the full-suite-before-commit gate.

## Before Crafting Commits or PRs

- **[600-git-conventions.md](600-git-conventions.md)** —
  branch naming, Conventional Commits, jargon and attribution prohibitions.
