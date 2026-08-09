# semantic-linefeeds

A multi-agent enforcement kit that makes coding agents actually follow
the semantic linefeeds convention ([SemBr](https://sembr.org))
in code comments, doc comments, docstrings, and Markdown prose.
It ships a Claude Code plugin, a Codex CLI hook, an opencode plugin,
and a portable AGENTS.md snippet for everything else,
all built on the same dependency-free Python detector.

Prose rules stated in CLAUDE.md or AGENTS.md fail at generation time:
the training prior is column-wrapped text, newlines are low-salience tokens,
and models cannot count characters.
This plugin therefore enforces the convention with three cooperating layers:

1. **Hook** —
   a post-edit hook runs a deterministic detector over the text just written to any supported source or Markdown file (see "Supported languages" below).
   Violations come back as feedback at the moment they happen,
   which is the only channel that survives long sessions.
2. **Skill** — `semantic-linefeeds` carries the judgment calls the detector cannot make:
   what counts as a clause boundary, the compound-object `and` test, the never-break list.
   The hook's feedback tells the agent to load it when needed.
3. **Detector** — `scripts/check_linefeeds.py`, dependency-free Python 3.
   Three precision-tuned heuristics:
   `fused` (two sentences on one line),
   `wrap` (a line severed mid-clause),
   `long` (>120 chars with a likely clause boundary).
   It only checks the text just written, never the rest of the file,
   so legacy column-wrapped files are not flagged into noisy rewraps.

## Install

Installation is per coding agent;
every path bottoms out in the same detector script.

| Agent | Install |
|---|---|
| Claude Code | Marketplace install below. |
| Codex CLI | `python3 scripts/install.py --codex` (manual steps: `adapters/codex/INSTALL.md`). |
| opencode | `python3 scripts/install.py --opencode` (manual steps: `adapters/opencode/INSTALL.md`). |
| Anything else | `python3 scripts/install.py --agentsmd` (snippet source: `adapters/agentsmd/SNIPPET.md`). |

### Claude Code (marketplace)

The repo embeds its own marketplace (`.claude-plugin/marketplace.json` with `source: "./"`),
so it installs from a local path or any private git remote — no public registry involved:

```bash
# from a local checkout
claude plugin marketplace add /path/to/semantic-linefeeds

# or from a private git remote
claude plugin marketplace add git@your-git.internal:arlo/semantic-linefeeds.git

claude plugin install semantic-linefeeds@semantic-linefeeds
```

## Supported languages

| Language | Extensions |
|---|---|
| Go | `.go` |
| C/C++ | `.c` `.h` `.cc` `.cpp` `.hpp` `.hh` |
| Java | `.java` |
| JS/TS | `.js` `.jsx` `.ts` `.tsx` `.mjs` `.cjs` |
| C# | `.cs` |
| Rust | `.rs` |
| Python | `.py` `.pyi` |
| shell | `.sh` `.bash` |
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

Fixtures under `tests/fixtures/<language>/` are plain source files with inline `{fused}`, `{wrap}`, or `{long}` markers,
which mark the lines that should be flagged;
the harness strips the markers before feeding the text to the detector,
then checks the reported findings against the marker positions.
`good_*` fixtures must carry zero markers —
a dedicated test enforces this so a "clean" fixture can never hide a real finding.
Bad fixtures are worked examples from the rule document this plugin grew out of;
good fixtures are their conformant counterparts plus every never-flag case
(directives, URLs, fenced code, tables, doc-comment example code).

The extractor (the layer that pulls prose spans out of source files) has its own golden tests:
`tests/extractor/in/` holds one source file per case,
and `tests/extractor/out/` holds the JSON list of prose spans it must extract.
After changing extraction logic, regenerate the goldens and diff-review the result:

```bash
python3 -m pytest tests/test_extractor.py --update-golden
git diff tests/extractor/out/
```
