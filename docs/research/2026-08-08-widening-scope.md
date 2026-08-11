# Widening scope: cross-agent portability, generic comment extraction, and test practice

Research date: 2026-08-08.
All claims below were checked against primary sources (official docs and source code);
each section cites the source that owns the claim.
Local context: this repo is a Claude Code plugin with a PostToolUse hook (`hooks/hooks.json`),
a skill (`skills/semantic-linefeeds/SKILL.md`),
and a dependency-free Python detector (`scripts/check_linefeeds.py`).

## 1. Cross-agent portability

### 1.1 Claude Code (baseline)

Source: https://code.claude.com/docs/en/hooks and https://code.claude.com/docs/en/plugins-reference

- Hook events include `PreToolUse`, `PostToolUse`, `PostToolBatch`, `UserPromptSubmit`, `Stop`, `SessionStart`, and ~25 others.
- Hooks are configured in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`,
  or bundled with a plugin as `hooks/hooks.json` (what this repo does).
- Command hooks receive JSON on stdin
  (`session_id`, `cwd`, `hook_event_name`, `tool_name`, `tool_input`, `tool_output`/`tool_response`, `tool_use_id`).
- Exit-code contract: exit 0 parses stdout as JSON control output;
  exit 2 is the "blocking error" channel with stderr fed to the model.
  For `PostToolUse` specifically, exit 2 cannot un-run the tool — it is advisory feedback the model sees —
  and JSON output supports `decision: "block"`, `reason`, `hookSpecificOutput.additionalContext`, and `updatedToolOutput`.
- Plugins are a directory with `.claude-plugin/plugin.json`, plus `skills/`, `hooks/hooks.json`, agents, and MCP/LSP servers;
  `${CLAUDE_PLUGIN_ROOT}` resolves to the installed plugin root, and `marketplace.json` handles distribution.
- Skills are `skills/<name>/SKILL.md` with `name`/`description` frontmatter.
- MCP is supported natively (project `.mcp.json`, plugin-bundled servers).

### 1.2 opencode (opencode.ai, sst/opencode)

Sources: https://opencode.ai/docs/plugins/ , https://opencode.ai/docs/rules/ , https://opencode.ai/docs/skills/ ,
https://opencode.ai/docs/mcp-servers/ ,
and `packages/plugin/src/index.ts` in https://github.com/sst/opencode

- Plugins are **in-process TypeScript/JavaScript modules**, not shell commands.
  They load from `.opencode/plugins/` (project), `~/.config/opencode/plugins/` (global),
  or npm packages listed under `"plugin"` in `opencode.json`; npm plugins are auto-installed via Bun.
- A plugin exports `async ({ project, client, $, directory, worktree }) => Hooks`;
  `$` is a Bun shell, so a plugin can shell out to an external CLI trivially.
- The `Hooks` interface (see `packages/plugin/src/index.ts`) includes
  `"tool.execute.before"?: (input: { tool, sessionID, callID }, output: { args }) => Promise<void>` and
  `"tool.execute.after"?: (input: { tool, sessionID, callID, args }, output: { title, output, metadata }) => Promise<void>`,
  plus `chat.message`, `chat.params`, `permission.ask`, `event`, and custom `tool` definitions.
- Blocking is done by **throwing** from a hook; advisory feedback is done by **mutating `output`**
  (e.g. appending to `output.output` in `tool.execute.after`, which is what the model sees as the tool result).
  There is no exit-code contract because there is no subprocess contract.
- Rules: project `AGENTS.md` (walking up to the git root), global `~/.config/opencode/AGENTS.md`,
  with explicit compatibility fallbacks to `CLAUDE.md` and `~/.claude/CLAUDE.md`,
  plus an `"instructions"` array in `opencode.json` supporting globs and URLs.
- Skills: opencode natively reads `SKILL.md` from `.opencode/skills/`, `~/.config/opencode/skills/`,
  **and the Claude-compatible locations** `.claude/skills/` and `~/.claude/skills/`, plus `.agents/skills/`;
  required frontmatter is `name` and `description`, surfaced to the model through a native `skill` tool.
- MCP: configured under the `"mcp"` key in `opencode.json` with `type: "local"` (command) or `type: "remote"` (URL).

### 1.3 Codex CLI (openai/codex)

Sources: https://learn.chatgpt.com/docs/config-file/config-reference (redirect target of the official developers.openai.com config reference),
https://learn.chatgpt.com/docs/agent-configuration/agents-md ,
and source files in https://github.com/openai/codex :
`codex-rs/hooks/src/events/post_tool_use.rs`, `codex-rs/hooks/src/engine/discovery.rs`, `codex-rs/features/src/lib.rs`.

The headline finding: **Codex now ships Claude-style lifecycle hooks, stable and on by default.**

- `codex-rs/features/src/lib.rs` defines the feature as
  "Enable Claude-style lifecycle hooks loaded from hooks.json files" —
  `id: Feature::CodexHooks, key: "hooks", stage: Stage::Stable, default_enabled: true`.
- Supported events (config reference): `PreToolUse`, `PostToolUse`, `PermissionRequest`,
  `PreCompact`, `PostCompact`, `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `UserPromptSubmit`, `Stop`.
  Only command hooks run today; "prompt and agent hook handlers are parsed but skipped".
- Config: a `hooks.json` file per config layer (user `~/.codex/hooks.json`, project `.codex/hooks.json`)
  or an inline `[hooks]` table in `config.toml`; both use the same event schema (`discovery.rs`, `load_hooks_json`).
- The `PostToolUse` stdin payload (`command_input_json` in `post_tool_use.rs`) is
  `{session_id, turn_id, agent_id?, agent_type?, transcript_path, cwd, hook_event_name: "PostToolUse", model, permission_mode, tool_name, tool_input, tool_response, tool_use_id}` —
  near-identical to Claude Code's, with `tool_response` for the tool result.
- Output contract (also `post_tool_use.rs`): exit 0 with JSON supporting `{"decision": "block", "reason": ...}`,
  `hookSpecificOutput.additionalContext`, and `continue: false` / `stopReason`;
  exit 2 with stderr becomes `HookRunStatus::Blocked` and the stderr text is fed back to the model —
  the same semantics as Claude Code, and the tests use matchers like `"Edit|Write"` and `"^Bash$"`.
- Two Codex-specific wrinkles:
  a **trust system** (unmanaged hooks are hashed and must be user-approved before they execute; `hook_trust_status` in `discovery.rs`),
  and per-hook `additionalContextLimit` token capping.
- Plugins: Codex has a plugin loader (`codex-rs/core-plugins/`),
  and `discovery.rs` injects `PLUGIN_ROOT` **and `CLAUDE_PLUGIN_ROOT`** env vars into plugin hook commands,
  with the source comment "For OOTB compat with existing plugins that use this env var" —
  i.e. Codex deliberately runs Claude-format plugins unmodified.
- Instructions: global `~/.codex/AGENTS.override.md` then `~/.codex/AGENTS.md`,
  then `AGENTS.override.md`/`AGENTS.md` at each level from the git root down to the cwd, concatenated root-down,
  capped by `project_doc_max_bytes` (32 KiB default), with `project_doc_fallback_filenames` configurable.
- Skills: Codex has skills (`docs/skills.md`, `skills.config` with per-skill `enabled`/`path` in `config.toml`).
- MCP: `mcp_servers.<id>` tables in `config.toml` (stdio `command` or HTTP `url`, tool allow/deny lists, timeouts).
- `notify` exists but is a UI notification command ("receives a JSON payload"), not an enforcement channel.

### 1.4 The AGENTS.md standard

Source: https://agents.md/

- Plain Markdown, no required fields, "a README for agents";
  created by OpenAI Codex, Amp, Google Jules, Cursor, and Factory,
  now stewarded by the Agentic AI Foundation under the Linux Foundation.
- Nested-file precedence: "the closest AGENTS.md to the edited file wins;
  explicit user chat prompts override everything".
- Adopted by 60k+ open-source projects and supported by Codex, Jules, VS Code, Copilot, Cursor, Zed, Aider, Devin, and others;
  opencode reads it natively (see 1.2).

### 1.5 How real cross-agent projects structure themselves

Evidence: https://github.com/obra/superpowers (repo root listing, README).

- Superpowers ships **one canonical `skills/` library** plus a thin adapter directory per harness:
  `.claude-plugin/`, `.codex-plugin/` (a single `plugin.json`), `.cursor-plugin/`, `.kimi-plugin/`,
  `.opencode/` (an `INSTALL.md` plus a `plugins/` dir with a JS shim), `.pi/`, `.agents/`,
  and pointer files `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, plus `gemini-extension.json`.
  The README supports 11 harnesses and states "Installation differs by harness.
  If you use more than one, install Superpowers separately for each one."
- So the hypothesis holds in practice:
  **shared core + thin per-agent adapters** is what the largest cross-agent skills project actually does.
- The ecosystem is also converging on Claude Code's formats as the interchange layer:
  Codex loads Claude-schema `hooks.json` and exports `CLAUDE_PLUGIN_ROOT` for plugin compat (1.3),
  and opencode reads `.claude/skills/` and `CLAUDE.md` (1.2).
  The one surface that does not converge is opencode's hook layer,
  which is in-process TypeScript rather than a subprocess JSON contract.
- MCP is universal across all three agents but is the wrong layer for *enforcement*:
  an MCP server exposes tools the model may choose to call;
  it cannot intercept the agent's own Edit/Write tools the way a PostToolUse hook can.
  It is a reasonable optional extra (a "check_prose" tool), not the portability backbone.

## 2. Generic comment/doc-prose extraction across languages

### 2.1 What the surveyed tools actually do

**Vale (errata-ai/vale) — the reference implementation for this problem.**
Sources: https://docs.vale.sh/formats/code.md , https://docs.vale.sh/topics/scopes.md ,
and repo `errata-ai/vale` (branch `v3`): `go.mod`, `internal/lint/code/*.go`.

- Vale lints comments in 25+ languages using **tree-sitter**:
  `go.mod` depends on `github.com/smacker/go-tree-sitter` (plus a Julia grammar package).
- Each language is one small file in `internal/lint/code/` declaring four things —
  e.g. `internal/lint/code/go.go` is just
  `Delims: regexp.MustCompile("//|/\\*|\\*/")`, `Parser: golang.GetLanguage()`,
  `Queries: [{Expr: "(comment) @comment"}]`, `Padding: cStyle`.
  Tree-sitter finds the comment nodes; the regex/padding layer strips markers and decoration.
- `internal/lint/code/comments.go` **coalesces consecutive line comments into one block**
  (merge only when comments are on consecutive lines at the same column offset — `doneMerging`),
  and records per-line `Strip` byte counts so alert positions map back to the original file.
- Comment scopes are `comment.line` and `comment.block`;
  embedded markup can be re-parsed as Markdown via a `[formats]` association (e.g. `rs = md`),
  "and every alert is mapped back to its original line and column";
  v3.17.0+ strips leading `*` decoration from C-style block comments first.

**gofmt / godoc.** Source: https://go.dev/doc/comment

- Since Go 1.19 gofmt canonicalizes doc comments,
  but "Gofmt preserves line breaks in paragraph text: it does not rewrap the text.
  **This allows the use of semantic linefeeds.**" — a direct endorsement of this plugin's convention.
- Directive comments (`//go:generate` etc.) are excluded from rendered docs and moved to the end of the doc comment.
- Structure recognition: indented (or specially marked) lines are code blocks;
  `*`/`-`/`+`/`•` and numbered markers open lists; `[Name]` and `[Text]: URL` are links.

**rustfmt.** Source: `Configurations.md` in rust-lang/rustfmt (sections `wrap_comments`, `comment_width`).

- `wrap_comments` (default `false`, unstable, tracking issue #3347) re-wraps comments to `comment_width` (default 80, also unstable).
- Documented never-wrap exceptions: "no wrapping will happen if:
  1. The comment is the start of a markdown header doc comment; 2. A URL was found in the comment."

**Prettier.** Source: https://prettier.io/docs/options (proseWrap section).

- `proseWrap` is `"preserve"` by default because "some services use a linebreak-sensitive renderer"
  (GitHub comments and BitBucket are named) — reflowing prose is treated as semantically unsafe by default.
- Prettier offers no option to reflow the text of code comments; comments pass through its printer as written.

**markdownlint (DavidAnson/markdownlint).** Source: `doc/md013.md`.

- MD013 (line-length) defaults to 80 and has independent switches for `code_blocks`, `tables`, and `headings`,
  separate length limits per construct,
  and built-in exemptions: lines with no split point (no whitespace past the limit) pass,
  and "link and image reference definitions are always exempted".
  `strict`/`stern` tighten those exemptions.

**mdformat.** Source: https://mdformat.readthedocs.io/en/stable/users/style.html

- By default mdformat "will not change word wrapping", explicitly to support Semantic Line Breaks;
  `--wrap` can be set to a width or `no`.
- Safety: the CLI "includes a safety check that will error and refuse to apply changes to a file
  if Markdown AST is not equal before and after formatting" — render-equivalence as a hard gate.

**docformatter (PyCQA/docformatter).** Source: repo `README.rst`.

- Python-docstring-only; formats to a subset of PEP 257 (summary line, blank line, closing quotes placement)
  with style awareness for Sphinx/Epytext field lists — a per-language formatter, not a generic extractor.

**sembr (admk/sembr).** Source: repo `README.md`.

- The ML approach: a finetuned masked-LM token classifier predicts a break-before label per token,
  with dynamic-programming break balancing.
- Cost: Python + PyTorch (or MLX on Apple Silicon), model weights, ~130 MB memory in the lightest variant;
  the README itself concedes break placement "could also be subjective".
  Far too heavy for a per-edit hook; interesting only as an offline reflow assistant.

**textlint.** Source: https://textlint.org/docs/plugin/

- Portability via **processor plugins**: each format plugin parses its input into a common TxtAST,
  and rules are written once against the AST, format-agnostically.
  This is the same shape as Vale's design (per-format front end, shared rule engine) in JS.

**proselint** operates on plain text and has no comment-extraction layer of its own.

### 2.2 Tree-sitter vs regex vs per-language parsers — practical tradeoffs

- Vale can afford tree-sitter because it ships a **compiled Go binary** with grammars linked in:
  zero install cost for users, all the weight paid at build time.
- For a Python script that must run as a lightweight hook, tree-sitter means
  `py-tree-sitter` plus a grammar bundle (C extensions, platform wheels) —
  it would end the current "dependency-free Python 3" install story
  (the hook currently runs with nothing but a system `python3`).
- Notably, even Vale needs its regex `Delims` layer on top of tree-sitter to strip markers and decoration;
  the parser only locates comments, it does not clean them.
- The failure mode of regex extraction is comment markers inside string literals
  (`s = "// not a comment"`), which a real parser avoids.
  For this plugin the risk is capped by design:
  the hook checks only the text just written, findings are advisory,
  and the heuristics are precision-tuned — a rare string-literal false positive is a nuisance, not a corruption.
- Sensible middle ground observed across tools:
  a small per-language table (line marker, block delimiters, doc-comment markers, decoration prefix)
  driving one shared state machine — Vale's per-language files are ~10 lines each for exactly this reason.

### 2.3 Distinguishing prose comments from code-ish comments (documented heuristics)

- **Directives:** Go defines directives as `//word:` with no space after `//` (go.dev/doc/comment);
  our detector's `GO_DIRECTIVE_RE` already matches this shape.
  Same family: `#!` shebangs, `# noqa`, `// eslint-disable`, `<!-- markdownlint-disable -->`.
- **URLs and markdown headers:** rustfmt refuses to wrap comments containing either (Configurations.md).
- **Code blocks in doc prose:** godoc treats indented lines as code (go.dev/doc/comment);
  never reflow indented material inside a comment.
- **Commented-out code:** ruff implements ERA001 (`crates/ruff_linter/src/rules/eradicate/`, fixtures dir `eradicate/`)
  as heuristics over the comment text — the existence of a dedicated rule shows this is detectable
  but fuzzy enough to deserve its own precision-tuned rule rather than an inline guess.
- **Unbreakable lines:** markdownlint MD013 skips lines with no whitespace past the limit
  and always exempts link/image reference definitions.
- **License headers:** no tool surveyed documents a special case;
  the pragmatic convention is positional (first comment block of the file) plus keyword match (`SPDX-License-Identifier`, `Copyright`).

### 2.4 Markdown specifics: what must never be reflowed

Converging list across markdownlint MD013, mdformat, and prettier:
fenced and indented code blocks, tables, YAML front matter, link/image reference definitions,
headings (length-limited separately, never wrapped), and inline HTML.
mdformat's AST-equality gate is the strongest safety pattern:
if a reflow would change the parsed structure, refuse to write.
Our detector already skips fences and front matter (`prose_lines_markdown` in `scripts/check_linefeeds.py`);
tables and reference definitions must stay on the never-flag list as scope widens.

## 3. Testing practices for linters/formatters

### 3.1 Golden/testdata patterns in the surveyed tools

**gofumpt (mvdan/gofumpt).**

- 41 files under `testdata/script/*.txtar` — one txtar archive per behavior
  (`comment-spaced.txtar`, `comment-code.txtar`, …), executed by the `testscript` runner;
  txtar (golang.org/x/tools/txtar) packs input files, commands, and expected output into one reviewable text file.
- `format/fuzz_test.go` seeds Go's native fuzzer with every `.go` file from the txtar corpus
  and asserts the formatter never errors on valid syntax —
  with `// TODO: verify that the result is idempotent` showing idempotency-under-fuzzing is the acknowledged next rung.

**Prettier.**

- Corpus layout: `tests/format/**` fixture directories, each with a `jsfmt.spec.js` declaring parsers/options,
  and jest `__snapshots__` holding the formatted output.
- The runner (`tests/config/format-test/run-test.js`) layers extra phases behind `FULL_TEST`:
  an "ast compare" phase and a **"second format"** phase.
- `tests/config/format-test/test-second-format.js` is the idempotency test:
  format the output again and `expect(secondOutput).toBe(firstOutput)`,
  with an explicit `unstableTests` list where the assertion is *inverted*
  so a fixed instability forces the entry's removal.

**ruff (astral-sh/ruff).**

- Fixtures: `crates/ruff_linter/resources/test/fixtures/<plugin>/<RULE>.py`
  (e.g. `pycodestyle/E501.py`), one file per rule/scenario.
- Tests: `#[test_case(Rule::LineTooLong, Path::new("E501.py"))]` cases in each plugin's `mod.rs` call `test_path` + `assert_diagnostics`,
  and expected diagnostics are **insta** snapshots in `src/rules/<plugin>/snapshots/*.snap`
  (verified: `ruff_linter__rules__pycodestyle__tests__E101_E101.py.snap` etc.).
  insta (https://insta.rs) provides the review/update workflow (`cargo insta review`).

**Vale.**

- Golden pairs for the comment extractor itself:
  `testdata/comments/in/0.go`, `1.rs`, `2.py`, `3.cpp`, `4.js`, `5.yml` → `testdata/comments/out/N.json`
  (verified in the `errata-ai/vale` v3 tree; exercised by `internal/lint/code/comments_test.go`).
  This is precisely the extractor-vs-checker seam this plugin needs.

**markdownlint.**

- Hundreds of fixture files under `test/`, one per rule/config permutation,
  with expected violations **annotated inline** in the fixture —
  `test/bare-urls.md` marks each offending line with `{MD034}` —
  plus per-directory `.markdownlint.json` configs.
  Fixture and expectation live in one file, which keeps review trivial.

### 3.2 Idempotency and property-based testing

- Formatters: prettier's second-format phase (3.1) is the canonical `format(format(x)) == format(x)` check;
  mdformat instead guards behavior with an AST-equivalence refusal (2.1);
  gofumpt fuzzes the formatter over its fixture corpus with idempotency as a stated TODO.
- For a pure *detector* (no fixer), the analogous property is:
  **conformant output must produce zero findings** —
  every `good_*` fixture is a no-findings assertion,
  and if a fixer is ever added, its output must immediately join the good corpus.

### 3.3 Minimal credible pattern for a Python-implemented checker

Synthesizing the above for pytest:

- `tests/fixtures/<lang>/` directories, one fixture file per behavior, named by intent
  (`bad_wrapped.go`, `good_directives.py`), exactly as this repo already starts to do.
- Two golden styles, used at two seams:
  Vale-style `in/` + `out/*.json` pairs for the *extractor* (positional data belongs in structured goldens),
  and markdownlint-style inline `{fused}`/`{wrap}`/`{long}` markers for *detector verdicts*
  (expectation next to the offending line, one file to review).
- A `--update-golden`/snapshot-refresh flag in `conftest.py`, mirroring `cargo insta review`'s workflow.
- Regression discipline from ruff/markdownlint: every false positive fixed becomes a permanent fixture.
- Adapter contract tests:
  recorded hook payloads (Claude Code JSON, Codex JSON, an opencode `tool.execute.after` args dump)
  stored as fixtures and replayed through each adapter entry point.

## Concrete recommendations

### Architecture: standalone core CLI + thin per-agent adapters

The evidence (superpowers' layout, Codex's deliberate Claude-compat, opencode's Claude-dir fallbacks) supports:

1. Keep **one core checker CLI** — `check_linefeeds.py`, still stdlib-only Python 3 —
   with a stable file-checking interface (`--file`, JSON output mode)
   and per-agent payload parsing behind explicit flags (`--hook claude`, `--hook codex`).
2. **Claude Code adapter:** the existing plugin, unchanged in shape.
3. **Codex adapter:** ship the same `hooks.json` schema
   (Codex loads Claude-style `hooks.json` from `~/.codex/hooks.json` / `.codex/hooks.json`, stable and default-on),
   and lean on `CLAUDE_PLUGIN_ROOT` compat for plugin distribution.
   The real porting work is not the hook contract — it is the **tool vocabulary**:
   Codex edits via `apply_patch`/`shell`, not `Edit`/`Write`,
   so the matcher and the `tool_input` parsing differ, and `tool_response` replaces `tool_output`.
   Budget for Codex's hook-trust prompt in the install docs.
4. **opencode adapter:** a ~30-line TypeScript plugin in `.opencode/plugins/` registering `tool.execute.after` for edit/write tools,
   shelling out to the core CLI via the provided Bun `$`,
   and appending findings to `output.output` (advisory, like our PostToolUse feedback).
   The skill needs no port: opencode already reads `.claude/skills/` and `~/.claude/skills/`.
5. **Every other agent:** an AGENTS.md snippet (the standard's nearest-file-wins semantics carry it into monorepos)
   plus the CLI invoked manually or from CI.
   Optionally expose the checker as an MCP tool later; do not build enforcement on MCP.

### Comment extraction: table-driven regex core, tree-sitter explicitly deferred

- Restructure the detector around Vale's proven decomposition:
  a per-language table (line marker, block delimiters, doc-comment forms, decoration prefix)
  feeding one shared extractor that yields `(comment_text, line_map)`,
  then one language-agnostic prose checker over the extracted text.
  Adopt Vale's two load-bearing details:
  coalesce only consecutive same-column line comments,
  and keep per-line strip offsets so findings map back to real positions.
- Stay regex/state-machine, not tree-sitter:
  the dependency-free install story is a core property for a hook,
  the hook only sees freshly written text, and findings are advisory —
  Vale shows tree-sitter pays off only when you can ship a compiled binary.
  Revisit only if whole-repo `--file` audits of string-heavy languages produce real false positives.
- Grow the never-flag list from the documented heuristics:
  no-space `marker+word:` directives (Go's rule generalizes), URLs and markdown headers (rustfmt),
  indented code inside doc comments (godoc), first-block license headers (SPDX/Copyright keywords),
  markdown tables and link reference definitions (MD013),
  and treat commented-out code detection as its own future precision-tuned rule (ruff ERA001 precedent).

### Test-suite layout

```
tests/
  fixtures/
    go/ …, python/ …, rust/ …, markdown/ …   # one file per behavior, bad_*/good_* naming
  extractor/
    in/  0.go 1.rs 2.py …                    # Vale-style golden pairs for extraction
    out/ 0.json 1.json …
  payloads/
    claude_posttooluse.json  codex_posttooluse.json  opencode_after.json
  conftest.py                                 # --update-golden flag
  test_detector.py  test_extractor.py  test_adapters.py
```

- Detector expectations move inline into fixtures as `{fused}`-style markers (markdownlint pattern);
  extractor expectations are JSON goldens (Vale pattern);
  adapters are tested by replaying recorded payloads.
- Standing invariants: every `good_*` fixture asserts zero findings,
  every fixed false positive adds a fixture,
  and if a fixer ever lands, add the prettier-style second-pass check on day one.
