# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **opencode now gets the judgment layer, not just the hook.**
  Until now `semlf install opencode` set up the checker and the plugin but no skill,
  while the hook still told the model to go read one.
  opencode installs its own skill from this release,
  so the advice it acts on is the same advice Codex gets:
  which `and` is a real clause boundary, what never to break, and when to stop and ask you.

- **A setup skill, so you can just ask your agent to install `semlf`.**
  Ask Claude Code, Codex CLI, or opencode to "install semlf",
  and it now follows a fixed procedure instead of guessing at package names or editing your config by hand.
  It installs the CLI if it is missing, repairs an install that went stale after an upgrade,
  and offers to write the project's `.semlf.ini`.
  It shows you every command before running it,
  and it will not overwrite one of your files or add an `exclude` line on its own —
  it shows you the difference and asks.
- **`/setup-semlf` in opencode.**
  opencode offers skills to the model and commands to you,
  so the same procedure is installed both ways and you can start it yourself by typing the command.

## [0.7.0] - 2026-08-14

`semlf` is now installable straight from PyPI.
`install`, `status`, `uninstall`, and `doctor` are the full lifecycle behind that one command.

### Added

- **`semlf` installs from PyPI**: `uv tool install semlf`,
  or the equivalent `pipx install semlf`.
  `semlf install` detects your agents and proposes one plan before writing anything,
  `semlf status` reports every artifact's state,
  `semlf uninstall` removes what was installed without touching anything it did not write,
  and `semlf doctor` replays a real edit through every installed hook end to end.
- **`.semlf.ini` can now opt a project into `wrap` feedback**:
  `experimental-wrap = true` does what
  `SEMLF_EXPERIMENTAL_WRAP=1` already did, project-wide.
  The environment variable still wins whenever it is set,
  so it can force `wrap` on or off regardless of what the file says.

### Changed

- **Hooks and skills now point at a shared install location outside any checkout**:
  `${XDG_DATA_HOME:-~/.local/share}/semlf/` holds the checker and README every installed hook and skill read,
  so an install keeps working even after the checkout that created it moves or is deleted.
- **Upgrading is one pair of commands**: `uv tool upgrade semlf && semlf install`.
- **A checkout install's hook now targets that same shared location, not the checkout itself.**
  `install.py --codex` used to point the Codex hook at a path inside the repository it ran from;
  it now points at the same shared copy a PyPI install writes,
  so the hook survives the checkout moving or being deleted.
- **`install.py --dry-run` reports a file that has diverged from what this kit installed,
  instead of failing.**
  It used to exit non-zero on a hand-edited skill or opencode file;
  it now prints the refusal it would make and exits 0, like any other preview.
- **A file this kit installed now upgrades in place, without `--force` and without a backup.**
  Only a hand-edited copy still needs `--force` to replace,
  and only that replacement still takes a backup first.
- **An existing backup file now blocks a forced replace instead of being silently overwritten.**
  `--force` used to overwrite a stale `.bak` left by an earlier forced replace;
  it now refuses whenever the backup slot is already occupied, the same way everywhere.
- **`install.py --codex` also publishes the checker and README to the shared install location.**
  A checkout install and a PyPI install now leave byte-identical copies behind.
- **Bare `install.py` status no longer probes `./AGENTS.md` in the current directory.**
  `semlf status agentsmd PATH` reports on a specific file instead.

### Fixed

- **The AGENTS.md snippet's install hint now names the published package.**
  It used to point at `install.py --cli`, a file only this repository has,
  so a repository that received the snippet told its users to run a command nobody said how to obtain.
  It now gives `uv tool install semlf` (or the equivalent `pipx install semlf`),
  which works from any repository now that the package is on PyPI.

## [0.6.0] - 2026-08-14

The checker now works as repository tooling, not only as editor hooks:
a standalone `semlf` command with git-aware modes, project configuration,
pre-commit integration, pipx and uv installation,
and a full install lifecycle with uninstall, doctor, and managed upgrades.

### Added

- **The `semlf` command**: `semlf check PATH...` (alias for `--file`),
  `--hook [claude|codex]`, `--json`, `--long-limit N`, and `--version`.
  Every diagnostic comes from the same single-file core the editor hooks run.
- **Project configuration**: `.semlf.ini` at the repository root,
  section `[semlf]`, key `long-limit`.
  The file is found by walking upward from the checked path
  and stopping at the first directory holding either the file or a `.git` entry.
  Precedence is the `--long-limit` flag, then `$SEMLF_LONG_LINE`,
  then the discovered file, then the default of 120.
  A broken file never breaks a run:
  an invalid value drops only its own key,
  and a missing or unreadable file falls through to the next source.
- **Git snapshot modes**: `--staged`, `--diff`, and `--changed` check a git snapshot instead of files named one by one —
  the staging area, unstaged edits, or everything changed since `HEAD`.
  Configuration is always read from the working tree,
  even when checking staged content.
- **Path excludes**: an `exclude` key in `.semlf.ini` filters hook and git mode discovery by folder or glob pattern.
  A path named explicitly with `--file` is always checked.
- **pre-commit integration**: a `.pre-commit-hooks.yaml` definition (`id: semlf`)
  runs `semlf --staged` in an environment pre-commit builds itself,
  so nothing has to be on `PATH` beforehand.
- **pipx and uv installation**:
  `pipx install git+https://github.com/arloliu/semantic-linefeeds`,
  or the equivalent `uv tool install`,
  installs `semlf` straight from the repository.
- **`install.py --cli`**: builds `semlf` as a self-contained zipapp
  and installs it at `~/.local/bin/semlf`,
  for machines and mirrors where pipx and uv are not available.
  Re-running is idempotent;
  `--force` replaces a copy whose content has diverged.
- **`install.py --auto`**: detects installed agents —
  a binary on `PATH` or the agent's own config directory —
  prints the evidence for each detection,
  and installs a matching mode for each agent found, plus the command itself.
- **`install.py --uninstall`**: removes an installed mode's artifacts.
  It checks everything before removing anything,
  edits shared files such as `hooks.json` or an AGENTS.md in place instead of deleting them,
  and refuses to remove a copy whose content it does not recognize.
- **`semlf doctor`**: verifies an install by replaying a real edit payload through every installed hook end to end,
  rather than only checking that files exist.
  It reports the platform, version, configuration, and excludes in force,
  and explicitly certifies or fails each hook.
- **Managed upgrades**: the installer records what it installed —
  path and content digest,
  one state file per artifact under `$XDG_STATE_HOME/semlf/artifacts/` —
  so an unmodified install from an earlier release upgrades in place without `--force`,
  while a hand-edited copy is refused until `--force` says to replace it.
- **Exclusive backups**: replacing a hand-edited `semlf` with `--force` first claims the `semlf.bak` slot exclusively,
  and refuses if a backup is already there,
  so two concurrent runs cannot overwrite the only backup.

### Changed

- **`install.py --agentsmd` requires an explicit target path.**
  It no longer defaults to `./AGENTS.md` in the current working directory,
  where a bare flag was more likely a mistake than a considered choice.
- **The AGENTS.md snippet now says `semlf --file <files you touched>`.**
  It previously pointed at a script path
  that only made sense inside a checkout of this repository.
- **`SEMLF_CHECKER` replaces `SEMANTIC_LINEFEEDS_CHECK`**
  as the opencode plugin's variable for pointing at an out-of-tree copy of the checker script.
  The old name still works as a deprecated alias;
  the new name wins when both are set.

## [0.5.0] - 2026-08-13

The two extraction defects the third holdout measured, repaired now that it is spent.
v0.5's architectural release: the span model, context-aware hooks, suppression,
and the judgment layer for every agent.

### Added

- **Every finding carries anchor, evidence, and ownership ranges** (ADR-0005).
  `diagnose(text, path, spans)` is the rich entry point,
  reporting only diagnostics whose ownership a changed span strictly touches,
  and `check` remains the tuple projection every existing consumer sees.
  A diagnostic whose ownership cannot be located exactly reports normally without spans
  and is withheld under them, because precision outranks recall.
- **A versioned diagnostic schema.**
  `--json` now emits `schema_version: 1` documents whose diagnostics carry the ranges,
  and the text renderer draws from the same structure.
- **Suppression directives** (ADR-0010): `semlf-ignore` and `semlf-ignore-next`,
  each scoped to exactly one line, standalone or trailing a comment leader.
  A recognized name with an unrecognized argument is malformed and wholly inert.
- **Context-aware hooks.**
  Both the Claude Code and Codex hooks now read a stable snapshot of the edited file,
  locate the edit inside it, and report real line numbers,
  where the Codex hook previously reported positions relative to the patch.
  Either falls back to the payload-only snippet report when the edit cannot be mapped onto the file.
- **A suggested replacement rides with a `!`/`?` fused finding** (ADR-0007).
  The automatic class stays restricted to `!` and `?`.
  A period boundary remains a suggestion only,
  since an abbreviation can never be proven safe by an allowlist.
  Hook feedback carries the exact two-line replacement for the agent's next edit,
  and nothing is written for it automatically.
- **A native Codex skill** (ADR-0006).
  `scripts/install.py --codex` now also writes
  `~/.agents/skills/semantic-linefeeds/SKILL.md`.
  Status, idempotent upgrade, and a `--force` divergence rule match the opencode installer.
- **The judgment layer reaches every agent** (ADR-0006).
  `SNIPPET.md` gains the compound-object `and` test,
  the clause-boundary definition, and the never-break list.
  The skill and the snippet both gain a bounded disagreement rule:
  judge a finding before rewriting,
  and a believed false positive,
  or a finding that survives one repair,
  goes to the user instead of another rewrite.
  Hook feedback carries the same rule,
  and names the skill only when a usable copy is present at a location Codex resolves skills from.

### Fixed

- **A spaced `gofail:` line is read as a directive.**
  A gofail failpoint is written `// gofail: var x T`,
  with a space the unspaced Go directive pattern never matches,
  so the line and the commented code under it reached the prose stream.
  The third round measured one wrap accusation on exactly that line;
  rechecking the pinned file removes it and one more of the same class, and adds nothing.
- **A Markdown paragraph carrying a licence marker is cut from the frame.**
  carbon-lang opens every Markdown file with a licence block inside an HTML comment,
  and five of its boilerplate units reached the third round's sampling frame.
  The paragraph cut that already silences licence text in code comments reaches Markdown now,
  so licence text is nothing to judge wherever it sits.

### Changed

- The `--json` output shape replaced `findings` records with `diagnostics` records.
  The version field exists so the next break announces itself.
- Hook feedback now ends with an instruction that an agent never adds a suppression directive on its own authority (ADR-0010).
  It is the last text of every report on both transports.
- The Codex hook's approximate-position footer now prints only on a degraded report,
  since a mapped report already carries real line numbers.

## [0.4.3] - 2026-08-12

The release that repairs what two spent holdouts left behind,
and the first whose finding-adding repairs were scored by a fresh sealed round before shipping.
Three of the first four items below were recorded as open defects when v0.4.2 shipped;
the fourth was found while repairing the third, and it corrects the record.
The fifth came out of diagnosing the second round's `fused` miss on the open data,
by rebuilding both spent draws from their pinned public sources.
A third holdout then cleared both floors it stated.

### Fixed

- **A build directive above a licence header no longer defeats the licence cut.**
  A Go build constraint is not a comment scope of its own,
  and reading it as one ended the leading region at the blank line the language requires under it.
  The licence below was then judged as prose:
  the same header yields no boundaries without the directives and six with them.
  A leading run of directives is stepped over,
  and only a run that actually opens with one, so a file that starts with a comment reads as before.
  `// +build`, the legacy form, is a directive too — it was not on Go's list at all.
- **A generated-file marker below a licence block is found.**
  Only the first five lines were read, and a licence header is longer than five,
  so `DO NOT EDIT` under one was missed.
  Every comment line above the first line of code is read now.
  That reach is added to the first five lines rather than replacing them,
  because narrowing the older rule would start checking files it now skips.
- **Code inside an HTML `<pre>` block in Markdown is not prose.**
  The opening tag was already skipped for starting with a bracket,
  and every line of code under it was read as prose.
- **A code fence is closed only by a run of its own mark, at least as long as its own.**
  One flag served both marks, so a tilde run inside a backtick block closed it,
  and a fence long enough to quote a shorter one was closed by the one it quoted.
  Either inverts every fence after that point in the file,
  so prose is skipped and the code in the next block is read as prose.

  This is one of two repairs here that add findings as well as removing them:
  prose the inversion was skipping is checked again.
  What could be measured before a round was:
  the frozen status of all 718 labeled units is unmoved,
  the compliant corpus is unmoved at eleven findings,
  and this repository's own files gain and lose nothing.
  The third holdout then scored it, below.
- **A `fused` stop is read across inline markup.**
  The rule required the sentence's final word to be all lowercase letters
  and the next sentence to open on an uppercase one,
  and Markdown prose that names APIs breaks both constantly.
  Three shapes are admitted:
  a sentence may end on a code span,
  close inside the emphasis it was written in,
  or hand off to a sentence that opens with a code span something follows.
  Emphasis before the stop stays outside the rule, so a bolded label beside a sentence stays quiet,
  and a bracketed enumeration and the lowercase guard that keeps `e.g.` out are both untouched.

  The widening is strict, so no finding the old rule reported is lost.
  Like the fence repair it adds findings the corpus in hand cannot score:
  the labeled corpus is unmoved at 31 of 37 and 169 of 220.
  The third holdout scored both repairs on the same terms, below.

### Measured

- **A third sealed holdout scored the fence repair and the markup repair, and both cleared.**
  356 boundaries from three sources fresh to the corpus — mebo, etcd, carbon-lang —
  drawn against a predicate frozen before any unit existed,
  labeled by three blind model families, adjudicated on 14 referrals, sealed, and opened once.
  Floors of 0.70 for `wrap` and 0.68 for `fused` were stated before the draw
  and carried no credit for either repair.
  The round returned 213 of 260 `wrap` and 69 of 82 `fused`,
  each lower bound nearly seven points above its floor.
  The Markdown `fused` stratum returned 50 of 59
  where the second round returned 25 of 47, the two intervals disjoint,
  so the publication block on `fused` rates is lifted for the predicate that ships.
  Four false positives in 360 labeled non-violations,
  none from either repair under test:
  three are the non-connector class
  [ADR-0002](docs/decisions/0002-wrap-withdrawn-from-default-feedback.md) records,
  and one is a `gofail:` directive reaching the prose stream,
  which is recorded with carbon-lang's HTML-comment licence block
  as the next extraction defects to cut.
- **The `fused` loss the second round reported is localized, without recovering a label.**
  Both spent draws were rebuilt deterministically from their pinned public sources,
  and every recorded Markdown miss fails one condition inside the fused rule,
  which is what the markup repair above answers.
  Whether that round's gap was its draw or the unlabeled population proxy is closed as unanswerable:
  its labels were deleted when the bundle was spent,
  and the question is moot for the predicate that ships.
- **The three false positives the second holdout found were recorded as one class, and only two are.**
  Both of those sit inside a `<pre>` block in one proposal.
  The third sits inside a fenced block the extractor believed was closed,
  which is a different defect and the fourth item above.
  [ADR-0009](docs/decisions/0009-a-round-scores-what-the-change-could-move.md)
  read that round on the false positive rate rather than the count,
  and on none of them coming from a line ending in a code span;
  both still hold.

## [0.4.2] - 2026-08-11

The release that reads what the labelers argued about.
Four of the five items below were found by people disagreeing over whether a line was prose,
rather than by any test in this repository.
[ADR-0008](docs/decisions/0008-a-holdout-is-spent-by-being-opened.md) records why that happened.

### Fixed

- **Commented-out code in a doc comment no longer wraps.**
  A worked example written as line comments never reaches the indented-example rule,
  so a lone closing brace formed a boundary with the call under it.
  A comment line holding nothing but code punctuation is not prose.
  Two wider rules were measured first;
  testing for an assignment or a call costs six labeled true violations,
  because prose names `AddStream()` and `Events()` the same way code does.
- **A Markdown table row may omit its leading pipe.**
  The delimiter row under the header now marks the block, since it is the one row that cannot read as prose.
  A pipe is required in that row too, so a setext underline still underlines.
- **A licence block below the code is cut like the one above it.**
  Only the leading comment region was cut before,
  and everything past it was judged as prose, licence sentences included.
  The corpus harness now calls the checker's cut instead of reproducing it.
- **A rule of repeated punctuation is a divider, not a sentence.**
  Three characters minimum, so an em dash standing alone is still the punctuation somebody wrote.

### Changed

- **A line ending in a code span is read by what stands in front of it.**
  The backtick is a legitimate line ender, so the clause the span was attached to was never examined.
  Two samples agreed on the cost: `wrap` recall there was 1 of 21 on one and 6 of 30 on the other.
  Six labeled violations moved from an accepted miss to detected,
  calibration `wrap` recall went from 163 of 220 to 169 of 220,
  and no labeled non-violation started drawing a complaint.

  A second sealed holdout scored it on prose nobody tuned it against:
  219 of 276, 79.3%, against a floor of 0.70 stated before the sample was drawn.
  The repair is monotone, since its pattern fires only where the line already ended in a backtick,
  so it can add a `wrap` finding and cannot remove one.
  Replaying both checkers over the labeled windows and over this repository's own Markdown removes nothing either time.
  It exposed seven `wrap` findings in this repository's own prose, and all seven are repaired:
  one in a decision record while the repair was being written, and six here.

### Measured

- **A second holdout was drawn, labeled, opened once, and spent.**
  386 boundaries and 772 records from three projects none of the earlier six shared an organization with,
  drawn against a predicate frozen before the sample existed,
  and the ordering is enforced by the draw and the seal rather than by the operator's care.
  `wrap` came back at 219 of 276 against a floor of 0.70, and `fused` at 50 of 77 against a floor of 0.68.

  The `fused` floor was missed, and the loss is entirely in Markdown:
  25 of 47, against 66 of 79 in the first round, while Go rose to 25 of 30.
  Nothing in this release changes how a fused line is found,
  so the miss is recorded against that heuristic and blocks any published `fused` rate.
  It cannot be localized from this round, whose labels were deleted when the bundle was spent.
  How a round is read when one floor clears and another does not is
  [ADR-0009](docs/decisions/0009-a-round-scores-what-the-change-could-move.md).

- **A missed floor is acknowledged in the corpus manifest or the suite fails.**
  A round states its floors before it is drawn and answers them once,
  and until now a `false` in a result file was consulted by nothing.
  Each miss now records what it is attributed to and what it blocks.

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
