# 100 - Project Map

Apply before changing any code.

## Layout

```
scripts/check_linefeeds.py        # the core: language table, extractor, checker, CLI, payload parsers
hooks/hooks.json                  # Claude Code adapter (PostToolUse → --hook claude)
skills/semantic-linefeeds/        # the skill agents load to fix findings
adapters/codex/                   # Codex CLI adapter (hooks.json template + INSTALL.md)
adapters/opencode/                # opencode TypeScript plugin + bun tests + INSTALL.md
adapters/agentsmd/SNIPPET.md      # paragraph for agents with no hook surface
tests/                            # pytest harness; see 300-testing.md
```

## The Core Stays One File

`scripts/check_linefeeds.py` is Python 3.9+ with stdlib imports only
(`argparse collections json re sys`).
Every adapter depends on the "copy one file, runs on bare python3" property;
adding a dependency or splitting the file breaks every install story at once.
Split into a package only if the file exceeds ~1000 lines.

## Invariants

- **Precision over recall.**
  The checker flags suspicion, the agent judges;
  when a heuristic is uncertain, skip the line.
  A miss is acceptable;
  a false positive is a bug.
- **Hook modes check only the text just written**, never the whole file;
  `--file` mode checks whole files,
  and its `long` findings never affect the exit code.
- **Exit codes are a contract.**
  `--file`: 0 clean, 1 violations or unreadable input.
  `--hook`: 0 clean or not applicable, 2 findings with stderr feedback.
  64 usage error;
  `--help` exits 0.
- **Adapters reuse the Claude payload contract.**
  Codex reads the same hook schema with `apply_patch` payloads;
  opencode builds a Claude-shaped payload and pipes it to `--hook claude`.
  Never invent payload fields no agent produces.
- `DEFAULT_LONG_LINE` (via `active_long_limit()`)
  and the `CONNECTORS`, `OK_LINE_ENDERS`, `FUSED_RE`,
  and `BOUNDARY_HINT_RE` heuristics keep their current semantics
  unless a change is the explicit point of the task.
