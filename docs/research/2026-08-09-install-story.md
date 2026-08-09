# Install story: patterns from superpowers and rtk, and a design sketch for semantic-linefeeds

Research date: 2026-08-09.
All claims below were checked against primary sources
(live repo source on GitHub via the `gh` CLI, a local release cache, and locally run `--help` output);
each section cites the source that owns the claim.
Local context: install today is entirely manual —
`adapters/codex/INSTALL.md` and `adapters/opencode/INSTALL.md` both instruct a human to clone the repo,
`cp`/`sed` files into place, and merge JSON by hand;
`adapters/agentsmd/SNIPPET.md` is a copy-paste block for any other agent;
Claude Code alone already has a real installer, because the repo embeds its own marketplace
(`.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`) and `README.md` documents
`claude plugin marketplace add` + `claude plugin install`.

## 1. github.com/obra/superpowers — multi-agent install story

### 1.1 Which harnesses it supports

Source: https://github.com/obra/superpowers/blob/main/README.md
and https://github.com/obra/superpowers/blob/main/docs/porting-to-a-new-harness.md

- The README's Quickstart line enumerates exactly 11 harnesses:
  Claude Code, Antigravity, Codex App, Codex CLI, Cursor, Factory Droid,
  Gemini CLI, GitHub Copilot CLI, Kimi Code, OpenCode, and Pi.
- `docs/porting-to-a-new-harness.md` Appendix A carries a smaller "reference integrations" table
  (Claude Code, Codex, Cursor, Copilot CLI, Gemini CLI, Kimi Code, OpenCode, pi) —
  Antigravity and Factory Droid are covered in prose elsewhere rather than in that table.
- Factory Droid is explicitly a non-port: the porting guide states
  "Factory's Droid, for example, consumes the Claude Code plugin via its own `plugin install` command
  and needs no new files here" — it rides the Claude Code manifest unmodified.
- The repo's own root-level manifests confirm five of these directly:
  `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, and `.agents/plugins/marketplace.json`
  (a generic marketplace manifest, distinct from `.claude-plugin/marketplace.json`),
  plus `gemini-extension.json`/`GEMINI.md`, `.opencode/`, and `.pi/`.

### 1.2 Install mechanism per agent

Source: https://github.com/obra/superpowers/blob/main/README.md (Installation section, read in full)

Every harness installs through **that harness's own plugin/extension command** — never a shell script this repo owns:

| Harness | Command | Manifest file(s) |
|---|---|---|
| Claude Code | `/plugin install superpowers@claude-plugins-official` (or `/plugin marketplace add obra/superpowers-marketplace` then `/plugin install superpowers@superpowers-marketplace`) | `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` |
| Antigravity | `agy plugin install https://github.com/obra/superpowers` | a generated `contextFileName` context file, staged by `.antigravity-plugin/install.sh` |
| Codex App | in-app Plugins sidebar, official Codex marketplace | synced fork, see 1.4 |
| Codex CLI | `/plugins` then search `superpowers` | `.codex-plugin/plugin.json` |
| Cursor | `/add-plugin superpowers` | `.cursor-plugin/plugin.json` + `hooks/hooks-cursor.json` |
| Factory Droid | `droid plugin marketplace add …` then `droid plugin install superpowers@superpowers` | none (reuses Claude Code's) |
| Gemini CLI | `gemini extensions install https://github.com/obra/superpowers` | `gemini-extension.json` + `GEMINI.md` |
| GitHub Copilot CLI | `copilot plugin marketplace add obra/superpowers-marketplace` then `copilot plugin install …` | shares the Claude Code hook path (`COPILOT_CLI` env var) |
| Kimi Code | `/plugins install https://github.com/obra/superpowers` or marketplace UI | `.kimi-plugin/plugin.json` |
| OpenCode | tell the agent to fetch and follow `.opencode/INSTALL.md` from the raw GitHub URL | `.opencode/plugins/superpowers.js`, declared via root `package.json`'s `main` field |
| Pi | `pi install git:github.com/obra/superpowers` | `.pi/extensions/superpowers.ts`, declared via `package.json`'s `pi` field |

`.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` and `.cursor-plugin/plugin.json`
and `.kimi-plugin/plugin.json` and `gemini-extension.json` were all read directly
(`gh api repos/obra/superpowers/contents/<path>`);
all five are pinned at `"version": "6.2.0"` as of this check,
consistent with the repo being mid-release at that version.

### 1.3 How the repo structures per-agent differences

Source: https://github.com/obra/superpowers/blob/main/docs/porting-to-a-new-harness.md

This is the closest thing to the "platform adaptation doc" the task asked about, and it is unusually explicit:

- Three components, cleanly separated: **skills** (`skills/`, harness-agnostic, "written to describe actions,
  never name a specific tool"), a **tool mapping** per harness
  (`skills/using-superpowers/references/<harness>-tools.md`, translating actions like
  "dispatch a subagent" into that harness's real tool name), and a **bootstrap** —
  the mechanism that injects the `using-superpowers` skill into context at session start,
  which the doc calls "the entire integration."
- Per-harness differences are collapsed into exactly **three structural shapes**:
  - **Shape A (shell-hook):** a hook system runs a command at session start and reads JSON from stdout.
    Reference: `hooks/session-start` (one script, detects the harness from env vars and emits
    one of three JSON shapes), `hooks/run-hook.cmd` (a Windows/Unix polyglot dispatcher),
    and per-harness hook configs `hooks/hooks.json` (Claude Code) / `hooks/hooks-cursor.json` (Cursor).
  - **Shape B (in-process plugin):** a JS/TS module with lifecycle callbacks that mutates the message array
    in code. Reference: `.opencode/plugins/superpowers.js` and `.pi/extensions/superpowers.ts`.
  - **Shape C (instructions-file):** no hook and no plugin —
    only an extension-declared context file the harness always loads.
    Reference: `gemini-extension.json`'s `contextFileName` field pointing at `GEMINI.md`,
    which is just two `@`-includes (the bootstrap skill and the tool-mapping reference).
- A hard, explicitly-stated invariant (Part 1, rule 2):
  "Everything ships through the harness's own install mechanism.
  Never edit the user's files.
  … A port **must not** reach into a user's global or personal config
  (`~/.gemini/config/AGENTS.md`, `settings.json`, `trustedFolders.json`, a hand-edited `~/.bashrc`, etc.)
  to inject anything."
  This is the single sharpest design contrast with rtk (section 2).
- A capability checklist gates whether a harness can be supported at all
  (automatic session-start injection is the one non-negotiable requirement);
  a harness where the human must opt in every session "cannot be properly supported."
- Distribution channels are enumerated per harness in Part 6 — a table covering native marketplace
  (Claude Code), an external-fork sync script (Codex, via `scripts/sync-to-codex-plugin.sh`,
  which rsyncs tracked plugin files into a separate fork repo and opens a PR),
  git-URL extension install (Gemini, Kimi Code, OpenCode), package-manifest fields (pi),
  and a local installer script (`agy plugin install` via `.antigravity-plugin/install.sh` for Antigravity).

### 1.4 Update and uninstall flows

Source: https://github.com/obra/superpowers/blob/main/README.md and repo-wide GitHub code search

- Update commands are documented per-harness where the harness has one:
  Gemini CLI has an explicit `gemini extensions update superpowers`;
  Antigravity's docs say "Reinstall with the same command to update."
  Claude Code, Cursor, Copilot CLI, Codex, and Kimi Code have no update command documented in the README —
  presumably each harness's native plugin-manager update path applies,
  but that is **unverified** from this repo's own docs.
- The README's own "Updating" section is deliberately vague:
  "Superpowers updates are somewhat coding-agent dependent, but are often automatic."
- **No uninstall flow is documented anywhere in the repo.**
  A GitHub code search scoped to the repo (`uninstall repo:obra/superpowers`) returned zero results.
  Removal is presumably left entirely to each harness's own plugin-uninstall command —
  this is consistent with rule 2 in 1.3 (the repo never writes user config, so it has nothing bespoke to clean up),
  but it is an absence, not a documented feature.

**Local cache cross-check:** `/home/arlo/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/`
matches the live repo where compared —
`.claude-plugin/plugin.json` is byte-identical (both report `"version": "6.2.0"`),
and `hooks/hooks.json` diffed byte-identical against the GitHub copy.
No disagreement found between the local cache and the live repo for the files checked.

## 2. github.com/rtk-ai/rtk — the `rtk init --xxx` pattern

### 2.1 Supported tools and exact flags

Source: https://github.com/rtk-ai/rtk/blob/develop/src/main.rs (the `Init` variant of the `Commands` enum)
and https://github.com/rtk-ai/rtk/blob/develop/docs/guide/getting-started/supported-agents.md

`rtk init`'s flags, read directly from the clap struct in `src/main.rs`:

```
-g, --global            add to global config dir instead of local project file
    --opencode          install OpenCode plugin (additive, alongside Claude Code)
    --gemini            target Gemini CLI instead of Claude Code
    --agent <AGENT>      claude | cursor | windsurf | cline | kilocode
                         | antigravity | kimi | pi | hermes | droid | vibe
    --show              show current configuration
    --claude-md         legacy mode: inject full instructions into CLAUDE.md
    --hook-only         hook only, no RTK.md
    --auto-patch        auto-patch settings.json without prompting
    --no-patch          skip settings.json patching, print manual instructions
    --trust-filters      / --no-trust-filters
    --uninstall         remove RTK artifacts for the selected mode
    --codex             target Codex CLI (AGENTS.md only, no hook patching)
    --copilot           install GitHub Copilot integration
    --dry-run           preview changes, write nothing
```

Sixteen harnesses total across the `--agent` enum plus the dedicated `--gemini`/`--codex`/`--copilot`/`--opencode` flags:
Claude Code (default), Cursor, Windsurf, Cline/Roo Code, Kilo Code, Antigravity, Kimi AI, Pi, Hermes,
Factory Droid, Mistral Vibe, Gemini CLI, Codex CLI, GitHub Copilot, OpenCode, plus OpenClaw
(installed via `openclaw plugins install ./openclaw`, entirely outside `rtk init`).

### 2.2 What `rtk init` actually does per tool

Source: https://github.com/rtk-ai/rtk/blob/develop/src/hooks/init.rs (8,387 lines, read directly)

The dispatch in `Commands::Init` (`src/main.rs`) routes to one function per tool in `src/hooks/init.rs`;
each does real, different filesystem work, not a shared template:

- **Claude Code (default mode, `run_default_mode`):** resolves `~/.claude/`
  via `resolve_claude_dir()` (honors `$CLAUDE_CONFIG_DIR`, falls back to `dirs::home_dir()`),
  reads `settings.json` as JSON (or starts from `{}`), and calls `insert_hook_entry`,
  which pushes a new object onto the `hooks.PreToolUse` array —
  `{"matcher": "Bash", "hooks": [{"type": "command", "command": hook_command}]}` —
  without touching any other entry already in that array.
  Idempotency is `hook_already_present`, which scans every existing `PreToolUse` hook's `command` string
  and matches on exact equality, a legacy-command-format check (`is_claude_hook_command`),
  or a substring match against the old shell-script filename (`REWRITE_HOOK_FILE`) —
  i.e. it recognizes both the current and a prior installed form as "already installed."
  It also writes a slim `RTK.md` (content is a `include_str!`-embedded constant, `RTK_SLIM`)
  and patches an `@RTK.md` reference into `CLAUDE.md`/`AGENTS.md`.
- **Codex CLI (`run_codex_mode` / `run_codex_mode_with_paths`):** writes `RTK.md` (the `RTK_SLIM_CODEX` variant)
  and patches an `@RTK.md` reference into `AGENTS.md` at either `~/.codex/` (global,
  via `resolve_codex_dir()` honoring `$CODEX_HOME`) or the project root.
  **It does not touch a Codex `hooks.json` at all** — `hooks/codex/README.md` confirms
  "Prompt-level guidance via awareness document -- no programmatic hook,"
  and the flag's own help text says "no Claude hook patching."
  Codex support is prompt-level only in rtk, unlike this repo's Codex adapter,
  which does register a real `PostToolUse` hook (see `adapters/codex/hooks.json`) — a genuine divergence;
  rtk's docs do not state a reason, so any inference about why is **unverified**.
- **opencode (`--opencode`, additive):** embeds `hooks/opencode/rtk.ts` at compile time
  (`const OPENCODE_PLUGIN: &str = include_str!("../../hooks/opencode/rtk.ts")`)
  and writes it to `~/.config/opencode/plugins/rtk.ts` via the same `write_if_changed` idempotent writer.
- **GitHub Copilot (`--copilot`):** writes a `PreToolUse` hook JSON to `.github/hooks/rtk-rewrite.json`
  (project scope) or `~/.copilot/hooks/rtk-rewrite.json` (global, honoring `$COPILOT_HOME`),
  plus an RTK block in `copilot-instructions.md`.
  The supported-agents doc notes a real regression fixed here: earlier versions registered a second,
  redundant camelCase `preToolUse` hook that Copilot CLI ran alongside the canonical one —
  a redundant process spawn with no behavioral benefit.
  The fix collapsed to a single hook, and `rtk init --copilot` re-run upgrades an existing install to it.
- **Factory Droid (`--agent droid`):** installs a `PreToolUse` hook into Droid's own `hooks.json`
  (`~/.factory/hooks.json` global, `.factory/hooks.json` project), falling back to the `hooks` key inside `settings.json` only when that file already carries live `PreToolUse` hooks —
  an explicit precedence rule against creating a second, conflicting hook file.
  It also reads Droid's own `commandDenylist`/`commandBlocklist` from all four Droid settings scopes and leaves matching commands untouched,
  so RTK never overrides Droid's native permission decisions.
- **Hermes (`--agent hermes`):** writes a Python plugin package to `~/.hermes/plugins/rtk-rewrite/` and enables it by patching `plugins.enabled` inside Hermes's own YAML config.
  The edit uses a hand-rolled YAML editor — about a dozen small functions such as `rewrite_hermes_config` and `find_yaml_key_line` — instead of a full YAML library.
  The goal is a minimal, reviewable text edit to one list, not a round-trip of the whole file.
  The plugin fails open: if `rtk` is missing at load time, the hook is not registered at all.
- **Mistral Vibe (`--agent vibe`, global-only):** appends a `[[hooks]]` TOML block to `~/.vibe/hooks.toml`,
  detected/kept unique by its `name = "rtk-rewrite"` field, plus a prompt file at `~/.vibe/prompts/rtk.md`
  (skippable with `--hook-only`); the installed hook entry sets `strict = false`
  so a crash in the hook degrades to a warning rather than blocking the tool call.
- **Cline, Windsurf, Kilo Code, Antigravity (rules-file agents):** each just writes one guidance file
  (`.clinerules`, `.windsurfrules`, `.kilocode/rules/rtk-rules.md`, `.agents/rules/antigravity-rtk-rules.md`)
  telling the model to prefer `rtk <cmd>` — no hook, no transparent rewrite;
  `docs/guide/getting-started/supported-agents.md` calls this the "Rules file" integration tier
  and is explicit that it is "guidance only."

### 2.3 UX details worth copying

Source: `src/hooks/init.rs`, functions `patch_settings_json_command`, `write_if_changed`,
`uninstall`, and the `PatchMode`/`PatchResult`/`InitContext` types.

- **Idempotent by content, not by "did I run before":** `write_if_changed` reads the target file if it exists,
  compares its content byte-for-byte against what would be written, and only writes (and only logs)
  when they differ — re-running `rtk init` with nothing to do is a silent no-op.
- **Three-way consent model (`PatchMode`):** `Ask` (default, interactive `[y/N]` prompt via
  `prompt_user_consent`), `Auto` (`--auto-patch`, no prompt), `Skip` (`--no-patch`,
  prints manual copy-paste instructions instead of writing).
  `--dry-run` explicitly **skips the interactive prompt** even in `Ask` mode
  ("we must not mutate state or block on stdin") and instead prints what it would have asked.
- **`--dry-run` is a first-class, pervasive flag, not bolted on:** every mutating path checks `ctx.dry_run` and prints a `[dry-run] would …` line instead of writing.
  A shared `print_dry_run_footer` prints `"\n[dry-run] Nothing written."` at the very end of every mode.
- **Backups before every settings.json mutation:** `patch_settings_json_command` copies the existing
  `settings.json` to `settings.json.bak` via `fs::copy` before the atomic write, and reports the backup path.
- **Atomic writes throughout:** `atomic_write` uses `tempfile::NamedTempFile` plus a rename,
  and `resolve_atomic_target` follows a pre-existing symlink first so the rename lands on the real file.
- **A real, scoped uninstall path:** `rtk init --uninstall [--global] [--agent …] [--codex] [--copilot] [--cursor] [--pi]` dispatches to a per-tool `uninstall_*` function.
  Each reports exactly what it removed as an itemized list, or "RTK was not installed (nothing to remove)" with the paths it checked.
  It respects `--dry-run` the same way install does, and is explicit about scope:
  only the RTK-owned block in `CLAUDE.md`/`AGENTS.md` (bounded by `<!-- rtk-instructions -->` / `<!-- /rtk-instructions -->` sentinel comments) is touched, leaving the rest of the file — and any other hooks in the same `hooks.toml`/`hooks.json` — untouched.
- **Status reporting is a flag, not a side effect:** `--show` prints current configuration without mutating anything.

### 2.4 Cross-check: local `rtk --help` against the source

The locally installed binary is `rtk 0.44.2` (`rtk --version`).
`rtk --help` and `rtk init --help` were run locally (read-only, no `rtk init` invocation was executed).

- Every flag in the local `rtk init --help` output matches the `Init` struct read from
  `src/main.rs` on the `develop` branch, including descriptions and the `--agent` value list.
- **One mismatch found:** the live `develop`-branch `AgentTarget` enum
  (`src/main.rs`, confirmed by a matching entry in `docs/guide/getting-started/supported-agents.md`'s
  Mistral Vibe section) includes a `Vibe` variant.
  The locally installed `rtk 0.44.2`'s `rtk init --help` lists only
  `claude | cursor | windsurf | cline | kilocode | antigravity | kimi | pi | hermes | droid` for `--agent` —
  **no `vibe`.**
  This is a version-lag mismatch (the local binary predates Vibe support landing in the live repo),
  not a hidden or undocumented flag.

## 3. Synthesis for semantic-linefeeds

### 3.1 Two install models, compared

- **superpowers: harness-owned marketplace + per-agent reference files.**
  The repo writes zero bytes into any user config, ever (docs/porting-to-a-new-harness.md, Part 1, rule 2).
  Every install is `<harness's own plugin command> <this repo's URL>`.
  The repo's job is to ship a manifest in the shape each harness's installer expects,
  plus a shared tool-mapping reference file per harness.
- **rtk: one binary, one `init --flag` subcommand that edits tool config directly.**
  The repo writes into `settings.json`, `hooks.json`, `hooks.toml`, `AGENTS.md`/`CLAUDE.md`,
  and even a YAML plugin-enable list — the exact class of action superpowers' porting guide forbids —
  but does it defensively: idempotent by content diff, backed up, dry-runnable, consent-gated, and uninstallable.
- **Tradeoff:** superpowers' model only works where a harness *has* a plugin/marketplace system at all
  (its own hard requirement in Part 2); where one exists, it is the cleaner, lower-risk choice —
  the harness's own installer owns correctness, versioning, and update/uninstall.
  rtk's model works on any harness that merely reads a config file, including harnesses with no plugin system whatsoever (Hermes's YAML, Vibe's TOML, Cline's `.clinerules`) —
  but it must carry, in this repo's own code, the full correctness burden (JSON/YAML/TOML merge semantics, backups, atomicity, path resolution) that superpowers gets for free from each harness's installer.
  Codex CLI is the case where the two projects made opposite choices with the same harness available to both:
  this repo already writes a real Codex `hooks.json` (`adapters/codex/hooks.json`); rtk deliberately does not,
  using AGENTS.md guidance only.

### 3.2 Sketch: an init-style installer for semantic-linefeeds

Grounded in what `adapters/*/INSTALL.md` currently tell a human to do by hand
(re-read in full at the start of this research), an installer's per-adapter job would be:

- **Claude Code:** already solved, superpowers-style — `.claude-plugin/marketplace.json` and
  `.claude-plugin/plugin.json` exist, and `README.md` already documents
  `claude plugin marketplace add` + `claude plugin install`.
  An installer adds nothing essential here; at most a `--show`-style status check
  (rtk's `--show` pattern) confirming the plugin is installed.
- **Codex CLI:** currently `adapters/codex/INSTALL.md` step 2 is a manual
  `sed "s|__REPO__|$HOME/tools/semantic-linefeeds|" adapters/codex/hooks.json > ~/.codex/hooks.json`,
  with the caveat "If you already have a `hooks.json`, merge the `PostToolUse` entry instead of overwriting"
  left entirely to the human.
  An installer would resolve `$CODEX_HOME` or `~/.codex/` (mirroring rtk's `resolve_codex_dir`), read any existing `hooks.json` as JSON, and check whether the `PostToolUse` array already has an entry whose command matches this repo's checker (rtk's `hook_already_present` pattern) —
  if not, it would append, never overwrite, a new entry.
  Step 3 of the same file is a hard limit an installer cannot script around:
  "Codex asks you to trust the hook on first run (unmanaged hooks are hashed and must be approved); accept it."
  An installer can only print that caveat, the same way the manual instructions already do.
- **opencode:** currently `adapters/opencode/INSTALL.md` step 1 instructs copying
  `adapters/opencode/semantic-linefeeds.ts` **and** `scripts/check_linefeeds.py` side by side into
  `~/.config/opencode/plugins/` or `<project>/.opencode/plugins/`.
  An installer would `mkdir -p` the target directory and content-diff-copy both files
  (rtk's `write_if_changed` pattern), and only copy `skills/semantic-linefeeds/` into
  `~/.config/opencode/skills/` if `.claude/skills/` isn't already visible to opencode
  (per `adapters/opencode/INSTALL.md` step 2, which notes opencode already reads Claude's skill paths natively).
- **Anything-else / generic agents:** `adapters/agentsmd/SNIPPET.md` is already written as a copy-paste block for a target `AGENTS.md`.
  An installer could append it idempotently using rtk's sentinel-comment pattern (`<!-- rtk-instructions -->` / `<!-- /rtk-instructions -->`, generalized to this repo's own marker),
  so a re-run neither duplicates the block nor disturbs the user's own surrounding content.

### 3.3 What could go wrong

- **Clobbering an existing `hooks.json`/`settings.json`:** a naive installer that reads, mutates, and dumps the whole file risks silently dropping keys it doesn't understand, if it round-trips through a data structure that isn't a faithful superset.
  rtk's fix is narrow: `insert_hook_entry` only ever pushes one new array element and never rewrites anything else in the object.
- **Overwriting a user-edited adapter file:** copying `semantic-linefeeds.ts` over a copy the user hand-patched would silently discard their edit.
  rtk's `write_if_changed` at least detects the diff and reports it; a stronger version could refuse to overwrite a changed file without `--force`, closer to `PatchMode::Ask`.
- **Wrong config path across OS/XDG variants:** hardcoding `~/.codex/` or `~/.config/opencode/` breaks for any user who has set `$CODEX_HOME` or otherwise relocated their config.
  rtk resolves every tool's home through an explicit env-var-override chain (`$CLAUDE_CONFIG_DIR`, `$CODEX_HOME`, `$HERMES_HOME`, `$FACTORY_HOME_OVERRIDE`), never a bare `~/`.
- **The Codex trust prompt cannot be scripted around** — see 3.2; an installer must document it,
  not attempt to suppress it, matching `adapters/codex/INSTALL.md`'s own current step 3.
- **Windows line-ending / extension traps:** superpowers' Part 7 records a real bug class here —
  a hook script named with a `.sh` extension gets double-invoked by Claude Code's Windows handling,
  which is why `hooks/session-start` is deliberately extensionless.
  Any future Windows-facing hook script in this repo should follow the same rule.
- **Fragile idempotency if the repo path moves:** matching only an exact command string breaks the moment a user relocates their checkout (the `__REPO__` substitution changes).
  rtk partially handles its own version of this with a legacy-path substring fallback (`cmd.contains(REWRITE_HOOK_FILE)`) as an upgrade path;
  a semantic-linefeeds installer would need an equivalent "recognize an older-form entry as already installed" rule if the on-disk path convention ever changes.

### 3.4 Open design questions (not resolved here)

- Should Claude Code stay purely marketplace-driven (zero write access, superpowers-style) while Codex/opencode/generic get an rtk-style file-writing installer —
  i.e., a *hybrid* strategy chosen per harness rather than one universal installer shape?
- Does a 3-adapter project need `--dry-run` and `--show` from day one (both proven useful in rtk),
  or is that premature machinery for this repo's current size?
- How should an installer detect "already installed" for the Claude Code path, where this repo doesn't own the merge logic at all (the harness's own plugin manager does),
  versus Codex/opencode, where this repo would own the merge logic directly?
- rtk carries no persistent install manifest — it re-derives idempotency by re-scanning each config file on every run.
  Is that sufficient here, or does this eventually want something like superpowers' `.version-bump.json` once there are more than a few adapters to keep in version-lockstep?
- rtk gates every `settings.json` write behind an interactive consent prompt by default (`PatchMode::Ask`),
  because its hook can rewrite/intercept commands.
  This repo's hook is advisory-only — it never blocks a tool call.
  Does that lower stake justify skipping the consent prompt (closer to `--auto-patch` as the default),
  or is a first-run confirmation still worth the safety margin regardless of blast radius?

### 3.5 Repo constraint: the detector must stay one stdlib-only file

This repo's convention — `scripts/check_linefeeds.py` is the one dependency-free Python 3 detector — is a constraint an installer must work around, not a decision this research resolves.
Two shapes are possible; neither is chosen here.

**Fold install into `check_linefeeds.py` itself, e.g. `--init codex`:**

- *Pros:* one file to vendor, curl, or pin — matching the existing "dependency-free Python 3" story;
  no second entry point to keep discoverable or in sync with the detector's own CLI surface;
  `--init` inherits the stdlib-only guarantee automatically, with no separate promise to keep.
- *Cons:* mixes two responsibilities — prose linting and filesystem-mutating installation — in one file,
  which cuts against this repo's own prior architecture guidance to keep the checker's interface stable
  and narrow (`docs/research/2026-08-08-widening-scope.md`, "Concrete recommendations" section);
  a security-sensitive file-writing code path (JSON merges, backups, path resolution across three-plus agents)
  becomes harder to review once it's interleaved with parsing and heuristics code;
  the file grows in a direction unrelated to what makes it a good detector.

**Ship a separate `scripts/install.py`:**

- *Pros:* clean separation — the detector stays pure and small;
  the installer is explicitly the file-mutating, higher-scrutiny surface, testable on its own (`tests/test_installer.py` rather than folding installer tests into `tests/test_cli.py`);
  it can still be stdlib-only Python 3 without touching the one-file convention, since that convention names `check_linefeeds.py` specifically.
- *Cons:* a second file to discover, document, and keep versioned in lockstep with the adapter files it installs (`adapters/codex/hooks.json`, `adapters/opencode/semantic-linefeeds.ts`) —
  the same two-source-of-truth drift risk rtk avoids by embedding its hook files as `include_str!` constants directly in the compiled binary;
  users now need to know two entry points exist instead of one.
