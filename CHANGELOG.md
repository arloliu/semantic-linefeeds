# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
