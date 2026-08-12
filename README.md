# semantic-linefeeds

> **AI coding agents know where a sentence ends — they just don't wrap lines there.**
> Trained on column-wrapped text, they default to breaking by character count instead of by meaning,
> and every diff suffers for it.

**The Problem:**

When comments and docs are wrapped to a fixed column width,
changing one word forces the whole paragraph to reflow,
and the diff for that one-word edit touches every line below it.

Telling a coding agent **"one sentence per line"** in your instructions doesn't fix this either —
the agent's training data is column-wrapped text,
newline characters carry little weight to a language model,
and it can't reliably count characters while it writes.

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

## Why Telling an Agent Isn't Enough

Writing the rule into AGENTS.md, CLAUDE.md, or any other instruction file doesn't hold up at generation time.

The model's training data is overwhelmingly column-wrapped,
newlines are low-salience to a language model,
and it can't count characters as it generates text.

This kit backs the rule with three layers instead of trusting the model to remember it:

1. **Hook** —
   a post-edit hook runs a deterministic detector over the text just written to any supported file.
   Violations come back as feedback the moment they happen,
   which is the one channel that survives a long session.
   Only `fused` stops the edit;
   a long line comes back as advice, because leaving it long is often the right answer.
   `wrap` is not reported to the model at all,
   because a labeled corpus measured its false positives and the number was not small enough to act on.
   Set `SEMLF_EXPERIMENTAL_WRAP=1` to see it anyway, as advice that never blocks.
2. **Skill** —
   `semantic-linefeeds` carries the judgment calls the detector can't make on its own:
   what counts as a clause boundary, the compound-object `and` test, the never-break list.
   The hook's feedback tells the agent when to load it.
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

## Quick Start

One command clones (or updates) a checkout under `${XDG_DATA_HOME:-~/.local/share}/semantic-linefeeds`
and hands the remaining arguments to `scripts/install.py`:

```bash
curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh | sh -s -- --codex
```

Pass the flag for your agent to the one-liner above, or to `python3 scripts/install.py` inside a checkout.
Passing no flag prints a status report of what's installed where.
Every path bottoms out in the same detector script.

| Agent | Installer flag | Guide |
|---|---|---|
| Claude Code | none | [marketplace commands below](#claude-code-marketplace) |
| Codex CLI | `--codex` | [adapters/codex/INSTALL.md](adapters/codex/INSTALL.md) |
| opencode | `--opencode` | [adapters/opencode/INSTALL.md](adapters/opencode/INSTALL.md) |
| Anything else | `--agentsmd [PATH]` | [adapters/agentsmd/SNIPPET.md](adapters/agentsmd/SNIPPET.md) |

### Claude Code (Marketplace)

The repo embeds its own marketplace (`.claude-plugin/marketplace.json` with `source: "./"`),
so it installs from a local path or any private git remote — no public registry involved:

```bash
claude plugin marketplace add /path/to/semantic-linefeeds
claude plugin install semantic-linefeeds@semantic-linefeeds
```

### Private Network

Everything installs from a mirror without edits.
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

## Configuration

The long-line advisory threshold defaults to 120 characters.
Set it per run with `--long-limit N` (0 disables the advisory),
or per environment with `SEMLF_LONG_LINE=N` — the flag wins over the environment variable.
Fused and wrap findings are never affected;
only the advisory threshold moves.

`SEMLF_EXPERIMENTAL_WRAP=1` puts `wrap` back in hook feedback,
where it arrives as advice at exit 0 and never blocks an edit.
Any value other than `0`, `false`, `no`, or `off` turns it on.

Hook mode skips paths under the platform temp directory and any `tmp/` component,
so agent scratch files are never flagged.
`--file` mode always checks exactly the paths you name.

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

## Testing

```bash
python3 -m pytest tests/ -q                        # full suite: CLI, detector, extractor goldens
python3 scripts/check_linefeeds.py --file <files>   # audit files by hand
bun test adapters/opencode/                         # opencode plugin's own unit tests (needs bun)
```

Detector fixtures live under `tests/fixtures/<language>/`;
inline `{fused}`, `{wrap}`, or `{long}` markers mark the lines that should be flagged.
`good_*` fixtures must carry zero markers, and a dedicated test enforces it.

The extractor has golden tests under `tests/extractor/`.
After changing extraction logic,
regenerate with `python3 -m pytest tests/test_extractor.py --update-golden` and diff-review the result.
