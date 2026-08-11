# Semantic-Linefeeds Agent Configuration

Authoritative entrypoint for coding agents in this repository.
`CLAUDE.md` points here;
other agents read `AGENTS.md` directly.
If instructions here conflict with a default behavior,
this file and the rules it references win —
only an explicit user instruction overrides them.

Semantic-linefeeds enforces one-thought-per-line prose in code comments, doc comments, docstrings, and Markdown.
One stdlib-only Python core (`scripts/check_linefeeds.py`) does all checking;
thin adapters connect it to Claude Code, Codex CLI, and opencode.

## Self-Hosting Rule

Every Markdown file in this repo must itself pass the checker:

```bash
python3 scripts/check_linefeeds.py --file <files you touched>
```

Zero `fused`/`wrap` findings before any commit;
`long` findings are advisories you judge, not obey.

Test data under `tests/` is the one exception, and it is not prose.
Those files exist to carry text the checker must flag or must leave alone,
so their findings are the measurement rather than a defect.
Write prose with semantic line breaks from the first draft:
one sentence per line,
and a long sentence splits only at a real clause boundary.

## Rules

Read [`.agents/rules/AGENTS.md`](.agents/rules/AGENTS.md) first —
it maps task triggers to the rule files that apply.

[`000-agent-contract.md`](.agents/rules/000-agent-contract.md) is always in force,
including its core rule:
**do not guess when source, tests, docs, `git`, or `grep` can answer.**

Two things to know before you touch code:

- **The core stays one file** ([`100`](.agents/rules/100-project-map.md)):
  `scripts/check_linefeeds.py`, Python 3.9+, stdlib imports only.
  Every adapter depends on the "copy one file, runs on bare python3" property.
- **Precision over recall** ([`100`](.agents/rules/100-project-map.md)):
  the checker flags suspicion and the agent judges;
  a missed finding is acceptable,
  but a false positive is a bug.

## Validation

Run before calling any work done:

```bash
python3 -m pytest tests/ -q
bun test adapters/opencode/        # when adapter TypeScript changed
python3 scripts/check_linefeeds.py --file <touched Markdown>
```
