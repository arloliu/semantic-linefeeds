# 100 - Project Map

Apply before changing any code.

## Layout

```
scripts/check_linefeeds.py        # the core: language table, extractor, checker, CLI, payload parsers
cli/semlf/                        # repository CLI (ADR-0004); delegates all analysis to the core
hooks/hooks.json                  # Claude Code adapter (PostToolUse → --hook claude)
skills/semantic-linefeeds/        # the skill agents load to fix findings
adapters/codex/                   # Codex CLI adapter (hooks.json template + INSTALL.md)
adapters/opencode/                # opencode TypeScript plugin + bun tests + INSTALL.md
adapters/agentsmd/SNIPPET.md      # paragraph for agents with no hook surface
tests/                            # pytest harness; see 300-testing.md
```

## The Core Stays One File

`scripts/check_linefeeds.py` is Python 3.9+ with stdlib imports only
(`argparse collections configparser fnmatch json os re sys tempfile`).
Every adapter depends on the "copy one file, runs on bare python3" property;
adding a dependency or splitting the file breaks every install story at once.

The old "split at ~1000 lines" threshold is withdrawn.
[ADR-0004](../../docs/decisions/0004-portable-core-and-repository-cli.md) replaced it.
The boundary is drawn by what a thing needs, not by how long the file has become:

- The **core** keeps extraction, the predicates, suppression semantics, span filtering,
  diagnostic construction, hook configuration discovery, project config discovery (`load_config`),
  and the hook entry points.
  Every adapter invokes the core without any CLI,
  so policy discovery living outside it would let hooks and CI disagree.
- A **repository CLI** would own git snapshot selection, subcommand routing,
  the installation lifecycle, doctor, and SARIF rendering.
  It reuses the core's discovery function rather than carrying its own.

A packaging proof under [`docs/proofs/zipapp-packaging/`](../../docs/proofs/zipapp-packaging/)
shows the split ships as one artifact, and one command replays it.
Line count is no longer the test.
The tests are executable:
copy the core alone into an empty directory, replay every adapter payload,
run it under Python 3.9, and reject any import outside the stdlib allowlist.

## Invariants

- **Precision over recall.**
  The checker flags suspicion, the agent judges;
  when a heuristic is uncertain, skip the line.
  A miss is acceptable;
  a false positive is a bug.
- Analysis may see the whole file:
  `diagnose(text, path, spans)` reads one stable snapshot.
- Reporting is restricted to diagnostics **owned** by a change:
  a diagnostic is reported under spans only when its ownership range touches a changed span or boundary (ADR-0005),
  and a diagnostic whose ownership could not be located exactly is withheld under spans rather than guessed at.
- Both hooks read the edited file and pass real spans into `diagnose`,
  with snippet mode (payload-only text) as the degraded fallback
  when the file can't be read or the edit can't be located in it.
- `--file` mode checks whole files,
  and `long` findings never affect the exit code in either mode.
- **Exit codes are a contract.**
  `--file`: 0 clean, 1 violations or unreadable input.
  `--hook`: 2 for a `fused` finding, with the report on stderr;
  0 for clean, not applicable, or advisories only.
  `wrap` never reaches hook feedback unless `SEMLF_EXPERIMENTAL_WRAP` is set,
  and it never blocks even then.
  64 usage error;
  `--help` and `--version` exit 0.
- **Status decides transport.**
  An advisory-only hook result exits 0
  and delivers its report as one JSON object on stdout,
  under `hookSpecificOutput.additionalContext`.
  Exit-0 stderr reaches no model in either host,
  so changing the status without the transport deletes the advice rather than unblocking it.
  Every hook entry point goes through `deliver()`;
  none of them prints directly.
- **Adapters reuse the Claude payload contract.**
  Codex reads the same hook schema with `apply_patch` payloads;
  opencode builds a Claude-shaped payload and pipes it to `--hook claude`.
  Never invent payload fields no agent produces.
- `DEFAULT_LONG_LINE` (via `active_long_limit()`)
  and the `CONNECTORS`, `OK_LINE_ENDERS`, `FUSED_RE`,
  and `BOUNDARY_HINT_RE` heuristics keep their current semantics
  unless a change is the explicit point of the task.
