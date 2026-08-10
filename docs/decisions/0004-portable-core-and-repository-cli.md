# ADR-0004: One portable core, one separate repository CLI

**Status:** accepted  
**Date:** 2026-08-10

## Decision

`.agents/rules/100-project-map.md:17-23` requires one Python 3.9+ stdlib-only core,
because every adapter copies and runs that file.
The core is at 747 lines against a ~1000-line split point.

### The split, and a packaging proof

- **Portable core** (`scripts/check_linefeeds.py`) keeps extraction, predicates, suppression semantics,
  span filtering, diagnostic construction, and the hook entry points.
- **Repository CLI** (`semlf`) owns git snapshot selection, subcommand routing,
  installation lifecycle, doctor, and SARIF rendering.
  Config *discovery* is not on this list;
  hook configuration discovery below places it in the core, and the CLI reuses that one function.

A proof of concept validates that this split is shippable as one artifact.
`python -m zipapp` produced a **10,465-byte** `semlf.pyz`,
carrying a core byte-identical to the repository copy, verified by `cmp`.

| Property | Result |
|---|---|
| Runs from an empty directory under `python3 -I -S` | Correct findings, exit 1 |
| Hook mode through the same artifact | exit 2, output identical to the core |
| `check --staged` against a divergent worktree | Reported the staged blob, ignored the clean worktree |
| Core copied alone, without the zipapp | Still runs, exit 1 |
| Python 3.9 syntax | All four modules parse at `feature_version=(3,9)` |
| Imports | `argparse collections json os re subprocess sys tempfile`, all stdlib |
| Startup cost | 22.6ms versus 16.4ms, median of 25 runs each, CPython 3.12.3, one machine |

The build recipe, the module sources, and the staged-repository fixture are checked in at
`docs/proofs/zipapp-packaging/`,
with the embedded core's digest as the identity check,
so the proof is reproducible rather than reported.
The archive's own digest is deliberately not asserted,
because `zipapp` embeds modification times and it therefore varies between builds.
One command rebuilds the artifact and replays the functional boundary rows.
The isolated-run row is asserted by exit status rather than by finding identity,
and the startup timing row is recorded separately rather than replayed.

Two limits are recorded honestly:
3.9 was checked for **syntax only**, since no 3.9 interpreter was available;
and the 6.2ms zipapp overhead is irrelevant for a CLI but would need re-evaluation
if hooks were ever routed through the archive.

The vague line-count threshold is replaced by executable tests:
copy the core alone into an empty directory, replay every adapter payload,
run it under Python 3.9, and reject any import outside a stdlib allowlist.

### Hook configuration discovery

Every adapter invokes the core **without** the repository CLI
(`hooks/hooks.json:5-9`, `adapters/codex/hooks.json:5-9`,
`adapters/opencode/semantic-linefeeds.ts:42-60`).
Leaving policy discovery to the CLI alone would let hooks and CI disagree,
which is the failure that destroys trust in a linter.

Decision: the **core** carries one small stdlib-only discovery function,
with an explicit start directory, precedence order, and parse-failure behavior.
The CLI reuses it rather than owning a second one.
Hook and CLI tests run against the same parsed configuration model.
