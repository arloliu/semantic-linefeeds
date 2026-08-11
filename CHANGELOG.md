# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-08-11

The release that measured itself.
A corpus of 359 boundaries from six projects was labeled by three model families
and settled by the maintainer, independently of anything this tool reports.
Every number below is measured against those labels rather than against the checker's own output.

### Changed

- **`wrap` no longer reaches the model.**
  It misfired on six of 450 labeled non-violations,
  and a kind that complains about correct prose cannot be the kind that refuses an edit.
  `fused` is now the only finding that exits 2.
  `SEMLF_EXPERIMENTAL_WRAP=1` puts `wrap` back as advice that never blocks,
  and `--file` audits keep it unconditionally.
- Hook mode's advisory wording asks for a judgment rather than a rewrite,
  because a finding this release could not trust must not be delivered as an instruction.

### Fixed

- **Abbreviations no longer read as fused sentences.**
  `cf.`, `esp.`, `viz.`, and `vs.` are excluded,
  derived from the rule they amend rather than from a list of abbreviations.
- **Closing emphasis no longer hides terminal punctuation.**
  `**required.**` ends in a full stop.
  Only a delimiter something opened is peeled, and a code span is never touched.
- **A list item is no longer measured against the next one.**
  Every item starts a new paragraph; continuation lines inside one item do not.
- **A blockquote no longer strips a line of every exemption it would have unquoted.**
  The markers used to come off after every rule had already run against them,
  so fenced code, indented code, headings, tables, reference definitions,
  and inline HTML all reached the detector as prose once quoted.
- `--file --json PATH` parses.
  An option word standing where a path belongs used to leave `--file` with nothing to consume.
- **The hook fails open on a payload of the wrong shape.**
  Attribute access was reached unguarded by JSON that parsed into a list, a number,
  or an object whose fields held the wrong type,
  so the hook exited 1 with a traceback on an edit it was only meant to inspect.

### Added

- A labeled corpus, its manifest, and a sealed-holdout mechanism,
  with recall recorded as floors per kind and per stratum
  so a loss of recall fails a run rather than passing quietly.
- A compliant corpus of prose that must draw no complaint, and a positive control that proves the gate can hear.

### Measured

- Recall against the labels: `wrap` 163 of 220, `fused` 31 of 37.
- False positives: one of 450 labeled non-violations, down from seven.
- Sixty-three true violations the checker does not report are recorded as accepted misses rather than hidden.
- The list-item repair cost two detections and removed four false positives.
  That trade is priced in the manifest instead of being absorbed.

### Scored against a sealed holdout

376 boundaries from three projects this tool had never been run against,
drawn after the predicate was frozen and opened once after the repairs were done.

| | calibration | holdout |
|---|---|---|
| `wrap` | 163 of 220, 74.1% | 231 of 311, 74.3% |
| `fused` | 31 of 37, 83.8% | 81 of 100, 81.0% |
| false positives | 1 of 450 | 1 of 331 |

Both floors were stated before the holdout existed, and both are met.
The rates land on top of the corpus the repairs were tuned against,
which is the claim this mechanism was built to be able to make.

## [0.4.0] - 2026-08-09

### Added

- Ten new comment languages:
  VB.NET, SQL, Lua, Ruby, Perl, PowerShell, R, Haskell, Elixir, and Zig,
  plus new C-family extensions
  (Kotlin, Swift, Scala, Dart, Objective-C, PHP, Groovy/Gradle).
- Configurable long-line advisory threshold:
  `--long-limit N` flag and `SEMLF_LONG_LINE` env var, 0 disables;
  default stays 120.
- `install.sh`: a curl-able POSIX bootstrapper.
  It clones or updates a checkout under `${XDG_DATA_HOME:-~/.local/share}/semantic-linefeeds`,
  then hands the remaining arguments to `scripts/install.py`.
  `--repo`/`--home`/`--ref` (or `SEMLF_REPO`/`SEMLF_HOME`/`SEMLF_REF`)
  override the clone source, checkout location, and pinned ref for mirrors and reproducible installs.
- README rewritten around the install story:
  the curl one-liner leads,
  every adapter row links to its install guide,
  and a private-network path (mirror via `--repo`/`SEMLF_REPO`,
  Claude Code via a private marketplace remote) is documented.

### Fixed

- Hook mode no longer flags files under the platform temp directory
  or any `tmp/` path component,
  so agent-generated scratch and prompt files pass untouched.

## [0.3.0] - 2026-08-09

### Added

- `scripts/install.py`:
  a stdlib-only installer for the Codex (`--codex`), opencode (`--opencode`),
  and AGENTS.md (`--agentsmd`) adapters,
  with append-never-overwrite JSON merging, `.bak` backups, atomic writes,
  `--dry-run`, `--force`, and a no-argument status report.
  Claude Code stays marketplace-installed and is never touched.

## [0.2.1] - 2026-08-09

### Added

- The opencode adapter also checks `apply_patch` edits:
  models with native patch support get that tool instead of edit/write,
  and the adapter now routes its patch text through the core's codex parser.

### Fixed

- The opencode plugin crashed the opencode server at startup:
  the loader calls every module export as a plugin factory,
  and the extra `buildPayload`/default exports returned non-hook values.
  The module now has exactly one export.

## [0.2.0] - 2026-08-09

Widens the plugin along three axes:
agents (Claude Code, plus new Codex CLI and opencode adapters),
languages (Go and Markdown, plus C-family, Rust, Python, and shell),
and tests (a bash script replaced by a pytest harness).

### Added

- **C-family, Rust, Python, and shell support.**
  The core now checks comments in C, C++, Java, JavaScript/TypeScript, and C#,
  rustdoc line and inner doc comments,
  Python `#` comments and docstrings (with multi-line signature tracking),
  and shell comments —
  driven by one per-language table feeding a shared extractor.
- **Codex CLI adapter** (`adapters/codex/`):
  a Claude-schema `hooks.json` template
  and an `apply_patch` payload parser that keeps disjoint addition runs separate
  and follows `*** Move to:` renames.
- **opencode adapter** (`adapters/opencode/`):
  a TypeScript plugin that builds a Claude-shaped payload,
  shells out to the same core,
  and appends findings to the tool output only when the checker blocks.
- **AGENTS.md snippet** (`adapters/agentsmd/SNIPPET.md`) for agents with no hook surface.
- **CLI surface**:
  `--hook [claude|codex]` with bare `--hook` still meaning claude,
  `--json` output for `--file` mode,
  and defined exit semantics (64 on usage errors, `--help` exits 0).
- **Never-flag hardening**:
  license headers, doctest lines,
  fenced code and `<pre>` blocks inside doc comments,
  Markdown indented code and link reference definitions,
  generated-file detection over the first five lines,
  and a component-based path skip (`vendor`, `node_modules`, `testdata`, `fixtures`, ...) for hook modes.
- **pytest harness**:
  detector fixtures with inline `{fused}`/`{wrap}`/`{long}` markers,
  Vale-style extraction goldens refreshed via `--update-golden`,
  recorded hook payload replays,
  and a bun unit-test suite for the opencode plugin.

### Changed

- Comment extraction is table-driven:
  consecutive line comments coalesce into one paragraph only when they start at the same indentation column.
- The Claude hook command names its agent explicitly (`--hook claude`).

### Removed

- The bash test harness (`tests/run_tests.sh`), replaced by pytest.

## [0.1.1] - 2026-08-08

### Changed

- Long-line findings are advisories in `--file` mode and no longer affect the exit code.

## [0.1.0] - 2026-08-08

### Added

- Initial release:
  Claude Code plugin with a PostToolUse hook,
  the semantic-linefeeds skill,
  and a detector for Go comments and Markdown prose.
