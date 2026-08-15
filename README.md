# semantic-linefeeds

**AI coding agents know where a sentence ends — they just don't wrap lines there.**<br>
*Line breaks are for meaning, not margins.*

> **A diff-aware prose guardrail for AI coding agents and source repositories.**
> Instructions alone don't reliably prevent it,
> and a deterministic check at the tool boundary catches it.

**The Problem:**

When comments and docs are wrapped to a fixed column width,
changing one word forces the whole paragraph to reflow,
and the diff for that one-word edit touches every line below it.

Telling a coding agent **"one sentence per line"** in your instructions doesn't fix this either:
instructions alone do not reliably prevent non-semantic breaks,
however prominently the rule is stated.

**What This Kit Does:**

semantic-linefeeds enforces [semantic line breaks](https://sembr.org) at the moment text is written —
in code comments, doc comments, docstrings, and Markdown.

Because each line holds one sentence (or one clause of a long sentence),
an edit touches only the line whose meaning changed,
and `git blame` keeps pointing at the sentence that changed.

Adapters wire the same dependency-free Python detector into Claude Code, Codex CLI, opencode,
and — through a portable AGENTS.md snippet — any agent that reads instruction files.

## Why Semantic Line Breaks

[SemBr](https://sembr.org) breaks lines by meaning instead of by column:
one sentence per line,
and a long sentence splits only at a real clause boundary.
The rendered output doesn't change —
Markdown still joins the lines back into one paragraph.

The difference shows up in diffs.
Add two words near the top of a column-wrapped paragraph (wrapped at 72 characters here),
and the rewrap ripples through every line below it:

```diff
-The exporter batches metrics in memory, flushes them once per minute,
-and retries failed uploads with exponential backoff until the queue
-drains.
+The exporter batches metrics and traces in memory, flushes them once per
+minute, and retries failed uploads with exponential backoff until the
+queue drains.
```

The same edit under semantic line breaks touches only the one line whose meaning changed:

```diff
-The exporter batches metrics in memory,
+The exporter batches metrics and traces in memory,
 flushes them once per minute,
 and retries failed uploads with exponential backoff until the queue drains.
```

Reviewers see exactly the word that changed,
and blame on any sentence finds the commit that wrote it.

## Quickstart

```bash
uv tool install semlf        # or: pipx install semlf
semlf install                # detects agents, lists every path it would write, asks y/N
semlf doctor                 # replays the payloads end to end
```

Claude Code stays on its own plugin marketplace and is never touched by `semlf`:

```bash
claude plugin marketplace add arloliu/semantic-linefeeds
claude plugin install semantic-linefeeds@semantic-linefeeds
```

A local checkout works the same way — point the first command at its path instead:

```bash
claude plugin marketplace add /path/to/semantic-linefeeds
claude plugin install semantic-linefeeds@semantic-linefeeds
```

| Agent | Command |
|---|---|
| Codex CLI | `semlf install codex` |
| opencode | `semlf install opencode` |
| Claude Code | the marketplace pair above |
| Anything else (AGENTS.md) | `semlf install agentsmd PATH` |

`semlf install` with no target detects which agents are present
and proposes one plan covering all of them, then asks y/N.
Naming a target instead — `codex`, `opencode`, or `agentsmd PATH` — applies that one target immediately.

Pick one channel for the `semlf` command itself.
A zipapp left at `~/.local/bin/semlf` and a `uv tool install`/`pipx install` shim would otherwise shadow each other;
`semlf install`'s end-of-run `PATH` check, and `semlf doctor`, both name the collision when they see one.

## Letting the Agent Set It Up

Once any agent on the machine has been set up, the rest is something you can just ask for.
A `setup-semlf` skill installs alongside the judgment layer,
so an agent asked to install, repair, or reconfigure `semlf` follows a fixed procedure rather than guessing at a package name or hand-editing `hooks.json`.

In opencode, type the command:

```
/setup-semlf
```

In Codex CLI or Claude Code, ask in prose — "set up semlf in this project" is enough to load it.

It installs the CLI when it is missing, walking `uv`, `pipx`, `pip --user`, and the checkout door in that order.
It repairs an install left stale by an upgrade, which is the failure that actually recurs.
And it offers to write the project's `.semlf.ini`, though most projects need none.

Three things it will not do, whatever it is asked:

- **Overwrite one of your files.**
  A refusal from `semlf install` is shown to you with the difference, and `--force` stays yours to type.
- **Add an `exclude` line on its own authority.**
  Excludes suppress discovery, so the agent may transcribe one you dictate and never propose one itself.
- **Run anything before showing you the command.**

The first install on a fresh machine is still yours to run —
an agent cannot fetch a skill it does not yet have.
Use the Quickstart above, or the [checkout door](#air-gapped-and-mirror-installs) where there is no package index.

## What Gets Installed

| Component | Location | Purpose | Who needs it |
|---|---|---|---|
| Checker | `${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py` | The enforcement core every installed hook and skill runs | Codex CLI (the hook's target) |
| README | published beside the checker, at the same neutral root | Resolves the installed skill's suppression-rules link, even on an air-gapped machine | Codex CLI |
| Codex hook entry | `$CODEX_HOME/hooks.json` (default `~/.codex/hooks.json`) | Runs the checker after every edit; blocks `fused`, reports `wrap`/`long` as advice | Codex CLI |
| Codex skill | `~/.agents/skills/semantic-linefeeds/SKILL.md` | The judgment layer: clause-boundary calls, suppression syntax, the disagreement rule | Codex CLI |
| Codex setup skill | `~/.agents/skills/setup-semlf/SKILL.md` | Lets an agent install, repair, or configure `semlf` without improvising the commands | Codex CLI |
| opencode plugin | the opencode plugins directory (`$XDG_CONFIG_HOME/opencode/plugins`, default `~/.config/opencode/plugins`) | Wires the checker into opencode's edit/write/apply_patch tool output | opencode |
| opencode's checker copy | the same opencode plugins directory, beside the plugin | The plugin resolves its checker next to itself, not at the neutral root | opencode |
| opencode's README copy | the same opencode plugins directory, beside the checker | Resolves the opencode skill's suppression-rules link without a neutral root | opencode |
| opencode skill | `$XDG_CONFIG_HOME/opencode/skills/semantic-linefeeds/SKILL.md` (default `~/.config/...`) | The same judgment layer Codex gets, resolving opencode's own checker and README | opencode |
| opencode setup skill | `$XDG_CONFIG_HOME/opencode/skills/setup-semlf/SKILL.md` (default `~/.config/...`) | The same setup procedure, in opencode's own skills root so each agent owns its copy | opencode |
| opencode setup command | `$XDG_CONFIG_HOME/opencode/commands/setup-semlf.md` (default `~/.config/...`) | Makes `/setup-semlf` typeable: opencode offers skills to the model, commands to you | opencode |
| AGENTS.md snippet | the file you name with `semlf install agentsmd PATH` | The judgment layer for any agent with no native skill mechanism | Any AGENTS.md-reading agent |

On the package channel, the `semlf` package is the installer and cannot be skipped —
but its check commands (`semlf check`, `semlf --staged`, and so on) stay optional after that.
A guardrail-only machine that wants no CLI at all is the checkout door's offer instead:
`install.sh --codex`, with no `--cli`, writes the hook, the skill, and the neutral-root payloads, and stops there
(see [Air-gapped and mirror installs](#air-gapped-and-mirror-installs)).

## Why Telling an Agent Isn't Enough

Writing the rule into AGENTS.md, CLAUDE.md, or any other instruction file doesn't hold up at generation time:
agents keep producing non-semantic line breaks with the rule in plain sight.

So this kit backs the rule with three layers instead of trusting the model to remember it:

1. **Hook** —
   a post-edit hook runs a deterministic detector over the text just written to any supported file.
   Violations come back as feedback the moment they happen,
   which is the one channel that survives a long session.
   Only `fused` stops the edit;
   a long line comes back as advice, because leaving it long is often the right answer.
   `wrap` is not reported to the model at all,
   because a labeled corpus measured its false positives and the number was not small enough to act on.
   Set `SEMLF_EXPERIMENTAL_WRAP=1` to see it anyway, as advice that never blocks,
   or set `experimental-wrap = true` in `.semlf.ini` to opt a whole project in.
2. **Skill** —
   `semantic-linefeeds` carries the judgment calls the detector can't make on its own:
   what counts as a clause boundary, the compound-object `and` test, the never-break list,
   and the bounded disagreement rule —
   judge a finding before rewriting, and a believed false positive
   or a finding that survives one repair goes to the user instead of another rewrite.
   Claude Code ships it as a plugin skill;
   `semlf install codex` writes a native copy for Codex CLI;
   other agents fall back to the AGENTS.md snippet.
   Hook feedback names the skill only when a usable copy is present at a location
   Codex resolves skills from.
3. **Detector** —
   `scripts/check_linefeeds.py`, dependency-free Python 3.
   Three precision-tuned heuristics:
   `fused` (two sentences on one line), `wrap` (a line severed mid-clause),
   and `long` (over a configurable limit, default 120 chars, with a likely clause boundary).
   `--file` audits report all three, because an audit is read by the person who asked for it.
   The hook reads a stable snapshot of the edited file for context,
   so it can report a real line number and skip findings an edit didn't touch,
   and it falls back to checking only the text just written when that mapping fails.
   Either way, legacy column-wrapped files are never flagged into a noisy rewrap.

## Suppressing a finding

Two directives, each scoped to exactly one line:

- `semlf-ignore` — withholds every finding anchored on the line carrying it.
- `semlf-ignore-next` — withholds every finding anchored on the next line.

Standalone, on a line of its own:

```markdown
<!-- semlf-ignore-next -->
A line the checker will leave alone.
```

Trailing, after the line it judges:

```markdown
A long judged line that runs on past the limit. <!-- semlf-ignore long -->
```

A two-line `wrap` finding anchors on its upper line,
so a trailing carrier suppressing it must sit on that first line, not the second.

Each directive takes zero or more kind arguments (`fused`, `wrap`, `long`);
no arguments suppresses every kind on that line.
A recognized directive name with any unrecognized argument is malformed and inert —
it suppresses nothing, and the findings it would have hidden stay visible.

Suppression is user-directed.
An agent never adds a `semlf-ignore` or `semlf-ignore-next` directive on its own authority:
when it judges a finding to be a false positive,
it leaves the text as written and raises the disagreement with you instead.

## Suggested replacements

A blocking `fused` report on `!` or `?` carries an exact two-line replacement
when the split is unambiguous (ADR-0007):

```
Suggested replacement for line 12:
    Stop now!
    Go on.
```

The suggestion exists only for the `!`/`?` automatic class, never for a period boundary.
It is never applied for you —
apply it as your next edit, after judging the finding like any other.

## Configuration

`.semlf.ini` at the repository root holds every project setting the checker reads,
one `[semlf]` section, three optional keys:

```ini
[semlf]
long-limit = 100
experimental-wrap = true
exclude =
    docs/legacy/
    *.gen.md
```

- `long-limit` — the long-line advisory threshold, in characters (`0` disables the advisory).
  Precedence is the `--long-limit` flag, then `$SEMLF_LONG_LINE`, then this key,
  then the built-in default of 120.
  Fused and wrap findings are never affected — only the advisory threshold moves.
- `experimental-wrap` — opts `wrap` findings back into hook feedback,
  arriving as advice that never blocks an edit (ADR-0017).
  `$SEMLF_EXPERIMENTAL_WRAP` decides outright whenever it is set to a non-empty value —
  `0`, `false`, `no`, or `off` reads as off, anything else as on —
  so it can force the kind on for a repo that never opted in, or off for one that did.
- `exclude` — one glob pattern per line, matched per path segment;
  a trailing `/` names a folder, excluded at any depth unless an inner `/` anchors a chain at the config root
  (see "Excluding paths" below).

The flag and the environment variable always win over the file (ADR-0012).
The core discovers `.semlf.ini` by walking upward from the checked file
and stops at the first directory holding either the file or a `.git` entry,
so a config never leaks across a repository boundary.
A missing, malformed, or unparseable file is inert —
the checker falls back to the next precedence leg rather than failing the run,
and an invalid value in one key never silences another.

Hook mode skips paths under the platform temp directory and any `tmp/` component,
so agent scratch files are never flagged.
`--file` mode always checks exactly the paths you name.

### Excluding paths

`exclude` takes one pattern per line;
the three shapes below are worth seeing side by side:

```ini
[semlf]
exclude =
    vendor/
    docs/generated/
    *.generated.md
```

A trailing `/` names a folder — a bare name like `vendor/` excludes it at any depth,
while an inner `/` before the trailing one anchors a chain at the config root —
today the repository root, where `.semlf.ini` lives (ADR-0012) —
so `docs/generated/` excludes only that path, not `plugins/docs/generated/`.
A pattern without a trailing `/` is a glob:
with a `/` it must match the whole relative path, segment by segment;
without one, like `*.generated.md`, it matches any single path component at any depth.
Matching is case-sensitive everywhere.

Excludes filter **discovery only** — hook mode and the three git modes below.
A path you name explicitly on `--file` or `check` is always checked,
exclude or no exclude, because naming a path is the judgment call excludes exist to encode.
An agent never adds an `exclude` line on its own authority (ADR-0010's principle);
it raises the disagreement with you instead.

## Checking git snapshots

Three more modes check a git snapshot instead of files you name:

- `semlf --staged` checks the index — what `git commit` would record —
  reading each staged blob by its own object id.
- `semlf --diff` checks the worktree copy of every unstaged change against the index.
- `semlf --changed` checks the worktree copy of everything different from `HEAD`,
  staged and unstaged together.

All three accept `--json` and `--long-limit N`, the same as `--file`.
Only tracked changes are enumerated;
an untracked file needs `git add` before any mode can see it.
Symlinks are never checked, in any mode.

Policy — `.semlf.ini`, including `exclude` — is always read from the working tree,
even for `--staged`: its content is the index, but its policy is the checkout it runs in.
A config that is staged but not yet on disk does not yet govern `--staged` (ADR-0013).

### Pre-commit

```yaml
repos:
  - repo: https://github.com/arloliu/semantic-linefeeds
    rev: <tag>
    hooks:
      - id: semlf
```

`language: python` lets pre-commit build this repository into its own environment,
so `semlf` does not need to be installed or on `PATH` beforehand.

## Supported Languages

| Languages | Extensions |
|---|---|
| C, C++, Objective-C | `.c` `.h` `.cc` `.cpp` `.hpp` `.hh` `.m` `.mm` |
| Java, Kotlin, Scala, Groovy | `.java` `.kt` `.kts` `.scala` `.groovy` `.gradle` |
| JS/TS | `.js` `.jsx` `.ts` `.tsx` `.mjs` `.cjs` |
| C#, VB.NET | `.cs` `.vb` |
| Go, Rust, Zig | `.go` `.rs` `.zig` |
| Python | `.py` `.pyi` |
| Swift, Dart, PHP | `.swift` `.dart` `.php` |
| shell, PowerShell | `.sh` `.bash` `.ps1` `.psm1` `.psd1` |
| Ruby, Perl, Lua | `.rb` `.rake` `.pl` `.pm` `.lua` |
| SQL, R, Haskell, Elixir | `.sql` `.r` `.R` `.hs` `.ex` `.exs` |
| Markdown | `.md` `.markdown` `.mdx` |

## Recommended Instructions Companion

The one habit that survives inline generation belongs in your agent's global instruction file —
AGENTS.md for most agents, CLAUDE.md for Claude Code.
Everything else lives in the skill and the hook:

```markdown
## Comment and doc formatting

One sentence per line in all comments and Markdown (semantic linefeeds).
After writing any text block, act on whatever the linefeeds hook reports.
A blocked edit must be fixed; an advisory is a judgment call, and leaving the line alone can be right.
```

## Appendix

### Air-gapped and mirror installs

The package channel's `git+URL` form still works when a machine can't reach PyPI:

```bash
pipx install git+https://github.com/arloliu/semantic-linefeeds
# or
uv tool install git+https://github.com/arloliu/semantic-linefeeds
```

For a fully offline or mirrored network, the checkout door covers every artifact this kit installs.
One command clones (or updates) a checkout under `${XDG_DATA_HOME:-~/.local/share}/semantic-linefeeds`
and hands the remaining arguments to `scripts/install.py`,
the same shared lifecycle engine behind `semlf install`:

```bash
curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh | sh -s -- --codex --cli
```

Pass the flag for your agent to the one-liner above, or to `python3 scripts/install.py` inside a checkout.
Passing no flag prints a status report of what's installed where.

| Agent | Installer flag |
|---|---|
| Codex CLI | `--codex` |
| opencode | `--opencode` |
| Anything else | `--agentsmd PATH` |

Add `--cli` to build the `semlf` zipapp and install it as `~/.local/bin/semlf` —
the one channel that needs no package index at all,
and the one the package door deliberately has no equivalent for:
pipx, uv, and the zipapp all want the same `~/.local/bin/semlf` shim,
so building and removing the zipapp stays exclusive to the checkout door.

`install.sh` reads its clone source from `--repo` or the `SEMLF_REPO` env var,
and the checker itself never touches the network.
Mirror this repo to your internal git host,
curl the script from the mirror's raw endpoint,
and point `SEMLF_REPO` back at the mirror:

```bash
# GitLab raw path shown; Gitea/Forgejo use /raw/branch/main/ instead of /-/raw/main/
curl -fsSL https://git.internal/you/semantic-linefeeds/-/raw/main/install.sh |
  SEMLF_REPO=git@git.internal:you/semantic-linefeeds.git sh -s -- --codex
```

Export `SEMLF_REPO` once in your shell profile,
and every later re-run installs and updates from the mirror without repeating it.
`--ref`/`SEMLF_REF` pins a tag or branch;
`--home`/`SEMLF_HOME` moves the checkout.

For Claude Code,
`claude plugin marketplace add git@git.internal:you/semantic-linefeeds.git` covers the same case.

The [Vercel `skills` CLI](https://www.npmjs.com/package/skills) can fetch the judgment-layer skill on its own,
as a supplement rather than an install path.
It copies `SKILL.md` and nothing else,
so it cannot install the hook —
this kit's load-bearing layer, the one that surfaces findings at generation time —
and an agent that only has the skill this way still needs `semlf install` or the checkout door for the hook.

### Lifecycle

```bash
semlf install [TARGET...]     # detect agents and propose a plan, or apply one named target
semlf status [agentsmd PATH]  # report every discoverable or recorded artifact's state
semlf uninstall TARGET...     # preflight-then-apply removal of a target's artifacts
semlf doctor                  # replay a payload end to end, report evidence
```

Upgrading is a two-command pair:

```bash
uv tool upgrade semlf && semlf install
# or: pipx upgrade semlf && semlf install
```

The first command updates the `semlf` command itself, its embedded payloads included;
the second re-applies the current payload set over whatever is already installed.
Upgrades are provenance-aware:
re-running an installer replaces an untouched older release silently.
A release newer than the one already published is a downgrade and refuses by default;
`--force` states the intent and replaces it, no backup, since a managed file is never the only copy of anything.
An edited or unrecorded file always refuses first;
`--force` there takes an exclusive backup to `<name>.bak` before replacing it,
and an occupied backup slot refuses either way.

Uninstalling one integration never deletes the neutral root's published checker or README:
their independence from any single integration is the point of the neutral root,
so they are left in place once the last integration that used them is gone,
and `semlf status` lists the specific leftover file paths in one line for manual removal.

A zipapp left over from before this redesign is a migration case:
`semlf install` runs a `PATH` check at the end of every run
and warns when `semlf` on `PATH` is not the artifact that just ran;
`semlf status` and `semlf doctor` repeat the warning,
with the checkout-door removal pointer (`install.py --uninstall --cli`).

### Testing

```bash
python3 -m pytest tests/ -q                        # full suite: CLI, detector, extractor, install/doctor
python3 scripts/check_linefeeds.py --file <files>   # audit files by hand
bun test adapters/opencode/                         # opencode plugin's own unit tests (needs bun)
```

Detector fixtures live under `tests/fixtures/<language>/`;
inline `{fused}`, `{wrap}`, or `{long}` markers mark the lines that should be flagged.
`good_*` fixtures must carry zero markers, and a dedicated test enforces it.

The extractor has golden tests under `tests/extractor/`.
After changing extraction logic,
regenerate with `python3 -m pytest tests/test_extractor.py --update-golden` and diff-review the result.
