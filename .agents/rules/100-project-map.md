# 100 - Project Map

Apply before changing any code.

## Layout

```
scripts/check_linefeeds.py        # the core: language table, extractor, checker, CLI, payload parsers
cli/semlf/                        # repository CLI (ADR-0004); delegates all analysis to the core
cli/semlf/providers.py             # git snapshot providers (the only place git runs)
cli/semlf/doctor.py                # end-to-end replay diagnostics (ships in the artifact)
cli/semlf/manifest.py              # install provenance (read by installer and doctor)
cli/semlf/registry.py              # the one payload table: sources, members, destinations, transforms
cli/semlf/classify.py              # three-axis admission (object state x provenance x mode)
cli/semlf/lifecycle.py             # shared install/status/uninstall engine behind both doors
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
- The **repository CLI** (`cli/semlf/`) owns git snapshot selection, subcommand routing,
  doctor, and rendering.
  It reuses the core's discovery function rather than carrying its own.
- The **CLI also owns install, uninstall, and status**,
  because the registry embeds every payload in the wheel and the zipapp,
  so those verbs no longer need a checkout to copy from
  ([ADR-0016](../../docs/decisions/0016-one-entry-point-and-the-payload-registry.md)).
- `scripts/install.py` is the **checkout door**:
  a thin parser over the same shared lifecycle operations,
  keeping its whole flag vocabulary so `install.sh` is unaffected,
  and the only door that builds or removes the zipapp
  ([ADR-0016](../../docs/decisions/0016-one-entry-point-and-the-payload-registry.md)).

A packaging proof under [`docs/proofs/zipapp-packaging/`](../../docs/proofs/zipapp-packaging/)
shows the split ships as one artifact, and one command replays it.
Line count is no longer the test.
The tests are executable:
copy the core alone into an empty directory, replay every adapter payload,
run it under Python 3.9, and reject any import outside the stdlib allowlist.

## Invariants

- **Precision over recall.**
  The checker flags suspicion, the agent judges;
  when a heuristic is uncertain about *what is wrong with a line*, skip the line.
  A miss is acceptable;
  a false positive is a bug.
  One reading is exempt, and the exemption is written narrowly on purpose.
  An **advisory** kind may report the **physical length of the extracted prose** without a heuristic,
  because counting characters in the text a reader sees is not a judgment about that text.
  `long` is that kind and the only one:
  it reports every line past the limit and says whether it also found a boundary to name.
  Withholding the report made silence mean two things —
  "this line is fine" and "this line is long and I cannot see where it breaks" —
  and an agent told to rejoin a column-wrapped comment heard the second as the first.

  Three limits keep this from becoming a general licence,
  and each was named by a reviewer who tried to widen it:

  - **Advisory only.**
    A blocking kind may never be raised by a count.
    `long` never blocks (ADR-0001), which is what makes an over-long line with nowhere to break
    cost attention rather than a rejected edit.
  - **Length only, of the prose only.**
    Not a count of commas, of capitals, or of any other feature,
    which would be a guess about prose dressed as arithmetic;
    and not of `raw`, whose indentation and comment marker this release already removed from the
    measurement because counting them accused correct text.
  - **A heuristic may refine the message, never gate the report.**
    `long` consults the boundary hint to choose which advice to print.
    That is the difference between deciding *what to say* and deciding *whether to speak*,
    and only the second is exempt here.

  A finding that cannot meet all three stays under the rule above:
  when the heuristic is uncertain, skip the line.

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
- **Excludes filter discovery only.**
  The `.semlf.ini` `exclude` key governs hook mode and the git modes (ADR-0013);
  a path named explicitly on `--file` is always checked.
- **Exit codes are a contract.**
  `--file`: 0 clean, 1 violations or unreadable input.
  `--hook`: 2 for a `fused` finding, with the report on stderr;
  0 for clean, not applicable, or advisories only.
  `wrap` never reaches hook feedback unless `SEMLF_EXPERIMENTAL_WRAP` or the `.semlf.ini` `experimental-wrap` key opts in (env wins, ADR-0017),
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
