# Install UX Redesign — Design

**Status:** draft, awaiting review
**Date:** 2026-08-14

## Problem

Two defects in the current install experience,
both reported from a fresh-user reading of the README.

1. **No component model.**
   The README's "three layers" section explains design philosophy,
   not what gets installed, where, or who needs each piece.
   The `semlf` CLI is the worst case:
   it exists for humans and CI —
   manual audits, git modes, pre-commit, doctor —
   and no agent hook ever calls it,
   yet the Quick Start's first example is `--codex --cli` with no explanation,
   and two CLI channels (zipapp and pipx) appear later with a "pick one" warning.
2. **The install path is a three-hop black box.**
   `curl | sh` clones a hidden checkout under `~/.local/share/semantic-linefeeds`,
   then hands off to `install.py`,
   which writes files into several locations the user never sees named up front.

## Patterns adopted from the field

Three healthy READMEs were surveyed
(obra/superpowers, mattpocock/skills, headroomlabs-ai/headroom):

- **headroom** — a two-tier install document
  (a 60-second quickstart on top, exhaustive channel and corporate-network detail in an appendix),
  a `doctor` verification step inside the quickstart itself,
  and naming exactly which files an install touches.
  The more invasive the tool, the more disclosure it owes;
  this kit writes hook configs, skill files, and a bin executable,
  so it sits at the high-disclosure end.
- **superpowers** — installs organized per host agent,
  one short command block per agent, so the only decision is "which agent do you use".
- **mattpocock/skills** — the only survey entry that names channel conflict outright
  ("Pick one — installing both leaves you with every skill twice").

## Decision

### One entry point: install the tool, the tool installs the integrations

```bash
uv tool install semlf        # or: pipx install semlf
semlf install                # detects agents, installs for each, prints every path it writes
semlf doctor                 # replays the payloads end to end
```

- `semlf install` with no arguments detects installed agents and installs for each,
  printing every artifact path it writes.
- `semlf install codex opencode` installs explicitly named integrations.
- `semlf status` reports what is installed where
  (today's no-flag `install.py` report).
- `semlf uninstall codex` removes an integration,
  with ADR-0014's preflight-then-apply semantics unchanged.
- `--dry-run` and `--force` carry over with their current meanings.
- Claude Code stays on its plugin marketplace pair and is never touched by `semlf`;
  `semlf install` and `semlf status` print the two marketplace commands
  when Claude Code is detected.

### Payloads ship inside the artifact

The adapter payloads —
`adapters/codex/hooks.json`, `skills/semantic-linefeeds/SKILL.md`,
`adapters/opencode/semantic-linefeeds.ts`, `adapters/agentsmd/SNIPPET.md`,
and the checker itself —
are embedded into the wheel and the zipapp at build time,
drawn from their canonical repository locations
(ADR-0015's no-packaging-fork rule extends to them:
mapping or build-time inclusion, never a second copy in the tree).
A test pins byte-identity between the embedded payloads and their sources.
Total payload weight beyond the already-shipped checker is under 12 KB.

This dissolves the premise behind ADR-0014's verb split:
a pipx-installed `semlf` now has payloads to copy from,
so install, uninstall, and status move behind `semlf`.

### One implementation, two doors

The lifecycle code moves into `cli/semlf/` modules.
`scripts/install.py` remains as the checkout-side door for air-gapped and development use,
delegating to those modules the way it already imports `semlf.manifest`,
so there is one implementation behind both entrances.
`install.sh` keeps working unchanged (it execs `install.py`)
and is demoted to the air-gapped appendix in the README.

### Channels after the change

| Channel | Command | Audience |
|---|---|---|
| Package (primary) | `uv tool install semlf` / `pipx install semlf`, then `semlf install` | anyone whose machine reaches PyPI or a git host |
| Package from a mirror | same, with `git+ssh://git.internal/...` or an internal index | private networks |
| Checkout | `git clone` + `python3 scripts/install.py`, or `install.sh` | air-gapped machines, development |
| Claude Code | `claude plugin marketplace add` + `claude plugin install` | unchanged |

One channel per machine stays the rule,
surfaced by the same three refusals ADR-0015 already names
(pipx's own, `install_cli`'s, and doctor's PATH check).

### PyPI

`semlf` is unclaimed on PyPI as of 2026-08-14.
Publishing joins the maintainer release checklist —
a release act, exactly the boundary ADR-0015 draws;
repository automation still never builds or uploads a PyPI artifact.
The git-URL install remains fully supported and is the mirror story,
so private networks lose nothing.

### README restructure

Two tiers, in this order:

1. What it is and the diff argument (current opening, trimmed).
2. **Quickstart** — the three-line block above,
   plus the Claude Code marketplace pair,
   plus a per-agent table for readers who want exactly one integration.
3. **What gets installed** — a matrix: component × location × purpose × who needs it.
   The CLI row says plainly:
   for humans and CI; hooks never call it; skip it if you only want the guardrail.
4. The layers, suppression, configuration, and git-modes sections, as today.
5. **Appendix** — air-gapped and mirror installs
   (`install.sh`, `SEMLF_REPO`, the zipapp channel), lifecycle detail, testing.

A channel-conflict note sits with the quickstart:
one channel per machine, and `semlf doctor` names a collision when it sees one.

### ADR impact

- **ADR-0014** — amended:
  payload embedding removes the "no payload to copy from" premise,
  and the lifecycle verbs move behind `semlf`.
  Preflight-then-apply, the provenance manifest, backup semantics,
  and doctor's contract all carry over unchanged.
- **ADR-0015** — amended narrowly:
  the wheel and zipapp contents gain the embedded payloads;
  the maintainer-act PyPI boundary and the no-fork mapping rule stand.
- **ADR-0004** — reference update only.

## Non-goals

- No Node or npm channel.
  The Vercel `skills` CLI (`npx skills add`) installs skills only —
  it cannot install the hook, which is this kit's load-bearing layer —
  so at most the README mentions it as a skill-only supplement with that caveat stated.
- No change to the Claude Code install.
- No change to detector behavior, hook wire formats, or the one-file core rule.
- `semlf update` (headroom-style, channel-detecting self-update) is noted as a possible follow-up,
  not part of this slice.

## Testing

- Byte-identity test: embedded payloads match their canonical sources.
- The existing payload replay tests run against a wheel-installed
  and a zipapp-installed `semlf`, not only the checkout.
- `tests/test_packaging.py` extends to pin the payload data files.
- Doctor, PATH-collision, and provenance-manifest behavior keep their current tests.

## Sequencing

This is a full slice (CLI surface, packaging, ADR amendments, README rewrite),
sized like v0.6c.
Where it lands relative to the ADR-0011 gate review is a scheduling call for the owner;
nothing in it depends on the gate's outcome.
The README's component-model matrix and section reorder (tier 2 and 3 above)
could ship earlier as a docs-only change if a stopgap is wanted.
