# semantic-linefeeds

Column-wrapped prose turns a one-word edit into a rewrapped paragraph,
and coding agents ignore a "one sentence per line" rule the moment generation starts.
This kit enforces [semantic line breaks](https://sembr.org) at edit time
in code comments, doc comments, docstrings, and Markdown,
so prose edits stay one-line diffs and `git blame` keeps pointing at sentences.
It ships a Claude Code plugin, a Codex CLI hook, an opencode plugin, and a portable AGENTS.md snippet,
all built on the same dependency-free Python detector.

## Why semantic line breaks

[SemBr](https://sembr.org) breaks lines by meaning:
one sentence per line,
and a long sentence splits only at a clause boundary.
Rendered output is identical — Markdown joins the lines back into a paragraph.
The difference shows up in every diff:
add two words near the top of a column-wrapped paragraph (here, wrapped at 72)
and the rewrap ripples through every line below.

```diff
-The exporter batches metrics in memory, flushes them once per minute,
-and retries failed uploads with exponential backoff until the queue
-drains.
+The exporter batches metrics and traces in memory, flushes them once per
+minute, and retries failed uploads with exponential backoff until the
+queue drains.
```

The same edit under semantic line breaks touches the one line whose meaning changed:

```diff
-The exporter batches metrics in memory,
+The exporter batches metrics and traces in memory,
 flushes them once per minute,
 and retries failed uploads with exponential backoff until the queue drains.
```

Reviewers see the word that changed, and blame on any sentence finds the commit that wrote it.

## Why a prompt rule is not enough

Prose rules stated in CLAUDE.md or AGENTS.md fail at generation time:
the training prior is column-wrapped text, newlines are low-salience tokens,
and models cannot count characters.
This kit therefore enforces the convention with three cooperating layers:

1. **Hook** —
   a post-edit hook runs a deterministic detector over the text just written to any supported file.
   Violations come back as feedback at the moment they happen,
   which is the only channel that survives long sessions.
2. **Skill** — `semantic-linefeeds` carries the judgment calls the detector cannot make:
   what counts as a clause boundary, the compound-object `and` test, the never-break list.
   The hook's feedback tells the agent to load it when needed.
3. **Detector** — `scripts/check_linefeeds.py`, dependency-free Python 3.
   Three precision-tuned heuristics:
   `fused` (two sentences on one line), `wrap` (a line severed mid-clause),
   and `long` (over a configurable limit, default 120 chars, with a likely clause boundary).
   It checks only the text just written, never the rest of the file,
   so legacy column-wrapped files are not flagged into noisy rewraps.

## Quick start

One command clones (or updates) a checkout under `${XDG_DATA_HOME:-~/.local/share}/semantic-linefeeds`
and hands the remaining arguments to `scripts/install.py`:

```bash
curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh | sh -s -- --codex
```

Pass the flag for your agent to the one-liner, or to `python3 scripts/install.py` inside a checkout;
no flag prints a status report of what is installed where.
Every path bottoms out in the same detector script.

| Agent | Installer flag | Guide |
|---|---|---|
| Claude Code | none | [marketplace commands below](#claude-code-marketplace) |
| Codex CLI | `--codex` | [adapters/codex/INSTALL.md](adapters/codex/INSTALL.md) |
| opencode | `--opencode` | [adapters/opencode/INSTALL.md](adapters/opencode/INSTALL.md) |
| Anything else | `--agentsmd [PATH]` | [adapters/agentsmd/SNIPPET.md](adapters/agentsmd/SNIPPET.md) |

### Claude Code (marketplace)

The repo embeds its own marketplace (`.claude-plugin/marketplace.json` with `source: "./"`),
so it installs from a local path or any private git remote — no public registry involved:

```bash
claude plugin marketplace add /path/to/semantic-linefeeds
claude plugin install semantic-linefeeds@semantic-linefeeds
```

### Private network

`install.sh` reads its clone source from `--repo` or `SEMLF_REPO`,
so a mirror needs no edits —
curl the script from the mirror and point it back at the mirror:

```bash
curl -fsSL https://git.internal/you/semantic-linefeeds/raw/main/install.sh |
  SEMLF_REPO=git@git.internal:you/semantic-linefeeds.git sh -s -- --codex
```

`--ref`/`SEMLF_REF` pins a tag or branch;
`--home`/`SEMLF_HOME` moves the checkout.
For Claude Code,
`claude plugin marketplace add git@git.internal:you/semantic-linefeeds.git` covers the same case.

## Configuration

The long-line advisory threshold defaults to 120 characters.
Set it per run with `--long-limit N` (0 disables the advisory),
or per environment with `SEMLF_LONG_LINE=N`;
the flag wins over the environment variable.
Fused and wrap findings are never affected — only the advisory moves.

Hook mode skips paths under the platform temp directory and any `tmp/` component,
so agent scratch files are never flagged.
`--file` mode always checks exactly the paths you name.

## Supported languages

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

## Recommended CLAUDE.md companion

The one habit that survives inline generation belongs in your global CLAUDE.md;
everything else lives in the skill and the hook:

```markdown
## Documentation prose

One sentence per line in all comments and Markdown (semantic linefeeds).
After writing any prose block, fix whatever the linefeeds hook reports.
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
The extractor has golden tests under `tests/extractor/`;
after changing extraction logic,
regenerate with `python3 -m pytest tests/test_extractor.py --update-golden` and diff-review the result.
