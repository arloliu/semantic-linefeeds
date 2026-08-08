# semantic-linefeeds

A Claude Code plugin that makes agents actually follow the semantic linefeeds convention
([SemBr](https://sembr.org)) in Go comments, godoc, and Markdown prose.

Prose rules stated in CLAUDE.md fail at generation time:
the training prior is column-wrapped text, newlines are low-salience tokens,
and models cannot count characters.
This plugin therefore enforces the convention with three cooperating layers:

1. **Hook** —
   a `PostToolUse` hook on `Edit`/`Write` runs a deterministic detector over the text just written to any `.go` or `.md` file.
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

## Install (private network)

The repo embeds its own marketplace (`.claude-plugin/marketplace.json` with `source: "./"`),
so it installs from a local path or any private git remote — no public registry involved:

```bash
# from a local checkout
claude plugin marketplace add /path/to/semantic-linefeeds

# or from a private git remote
claude plugin marketplace add git@your-git.internal:arlo/semantic-linefeeds.git

claude plugin install semantic-linefeeds@semantic-linefeeds
```

## Recommended CLAUDE.md companion

The one habit that survives inline generation belongs in your global CLAUDE.md;
everything else lives in the skill and the hook:

```markdown
## Documentation prose

One sentence per line in all comments and Markdown (semantic linefeeds).
After writing any prose block, fix whatever the linefeeds hook reports.
```

## Development

```bash
tests/run_tests.sh          # fixture tests for the detector
python3 scripts/check_linefeeds.py --file <files>   # audit files by hand
```

The bad fixtures are worked examples from the rule document this plugin grew out of;
the good fixtures are their conformant counterparts plus every never-flag case
(directives, URLs, fenced code, tables, godoc example code).
