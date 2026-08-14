# Install UX Redesign — Design

**Status:** revised draft, awaiting review
**Date:** 2026-08-14

## Problem

Two defects in the current install experience,
both reported from a fresh-user reading of the README.

1. **No component model.**
   The README's "three layers" section explains design philosophy,
   not what gets installed, where, or who needs each piece.
   The `semlf` CLI is the worst case:
   its check commands exist for humans and CI —
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
semlf install                # detects agents, lists every path it would write, asks y/N
semlf doctor                 # replays the payloads end to end
```

Claude Code stays on its plugin marketplace pair and is never touched by `semlf`.

### The neutral payload root

Every installed hook and skill references the checker at one channel-neutral path:

```
${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py
```

`semlf install` publishes the checker there as a provenance-managed artifact,
whatever channel `semlf` itself arrived by —
wheel, zipapp, or checkout.
`README.md` is published beside it,
so the installed skill's suppression-rules link resolves to a local file
and keeps working on air-gapped machines.

The zipapp channel forces this shape anyway:
a hook cannot point into a `.pyz` archive,
so the checker must be published to a real path,
and when that path is the single target for every channel,
a hook survives a channel switch, a venv rebuild, or a CLI uninstall untouched.
The alternative — routing hooks through the `semlf` command itself —
was analyzed and rejected:
hooks run in the agent's environment, where `PATH` may lack the shim directory;
it would make the CLI a survival dependency of the guardrail
(uninstalling the CLI would silently kill enforcement for every agent);
and it would fork the hook shape between the package door and the checkout door,
against ADR-0004's rule that adapters invoke the core without the CLI.

One residual risk is accepted and mitigated:
after `uv tool upgrade semlf`,
the published checker lags until `semlf install` runs again.
`semlf status` and `semlf doctor` compare the published checker's version against the artifact's own and say so;
the documented upgrade command is the pair
`uv tool upgrade semlf && semlf install`.

### The payload table

One declarative table drives the wheel build, the zipapp build, and the installer,
so the three can never disagree about what a payload is:

| Payload | Canonical source | Installed destination | Rendering |
|---|---|---|---|
| checker | `scripts/check_linefeeds.py` | `<data root>/semlf/check_linefeeds.py` | byte copy |
| readme | `README.md` | `<data root>/semlf/README.md` | byte copy |
| codex hook | `adapters/codex/hooks.json` | merged into `$CODEX_HOME/hooks.json` | placeholder → neutral checker path |
| codex skill | `skills/semantic-linefeeds/SKILL.md` | `~/.agents/skills/semantic-linefeeds/SKILL.md` | three rewrites → neutral checker path and local README |
| opencode plugin | `adapters/opencode/semantic-linefeeds.ts` | opencode plugins dir, checker copied beside it | byte copy, both files |
| agentsmd snippet | `adapters/agentsmd/SNIPPET.md` | sentinel block in the path the user names | byte splice |

Two rows are transforms, not copies,
and the design owns that fact:
the installed codex hook entry is rendered from the canonical `hooks.json` template
(the installer stops constructing it programmatically,
so the canonical file and the installed entry cannot drift),
and the installed skill body is the existing three-rewrite transform with the neutral paths substituted.
The opencode plugin keeps its current side-by-side contract —
the plugin resolves the checker beside itself —
so its install copies both files, exactly as today.

The installed hook command keeps the shape
`python3 <path ending in check_linefeeds.py> --hook codex`,
so `parse_managed_codex_hook`'s structural ownership rule holds unchanged.

### Command surface

| Command | Behavior |
|---|---|
| `semlf install` | detect codex and opencode; print every path the plan writes; TTY: confirm `y/N`; non-TTY without `--yes`: print the plan, exit 1 with a `--yes` hint |
| `semlf install codex opencode` | naming a target is consent: apply directly, no prompt, TTY or not |
| `semlf install agentsmd PATH` | first-class; the path is required, never defaulted, never auto-detected |
| `semlf install --yes` | apply without prompting, any mode |
| `semlf install --dry-run` | print the plan, write nothing, exit 0 |
| `semlf status` | report every artifact's state (today's no-flag `install.py` report) |
| `semlf uninstall codex` | preflight-then-apply removal, ADR-0014 semantics unchanged |
| `semlf uninstall` (no target) | usage error, exit 64 |
| `semlf doctor` | unchanged |

Auto-detection covers codex and opencode only.
The agentsmd snippet is never auto-installed (its target cannot be detected),
and the zipapp never is (next section).
`--force` keeps its meaning under the upgrade state machine below.
Exit codes stay 0 success or no-op, 1 refusal or error, 64 usage —
the non-TTY unconfirmed plan exits 1
because a provisioning script that forgot `--yes` must fail loud,
not report green over an install that never happened.

When the `claude` binary is on `PATH` or `~/.claude` exists,
`semlf install` and `semlf status` end their output with the two marketplace commands,
visually set off as the last block
so multi-agent install output cannot scroll it away,
and a user cannot mistake Claude Code for something `semlf` configured.

### The zipapp stays behind the checkout door

The package door has no `cli` target:
pipx, uv, and the zipapp all want `~/.local/bin/semlf`,
and a package-installed `semlf uninstall cli --force` could unlink the very shim the running command came from.
Building and removing the zipapp remains exclusive to the checkout door
(`install.py --cli`, as today).
A zipapp left over from before this redesign is a migration case:
`semlf status` and `semlf doctor` report it,
name which file `PATH` actually resolves to,
and point at the checkout-door removal.

### One upgrade state machine for every recorded artifact

Today only the cli artifact honors ADR-0014's managed-upgrade rule;
the codex skill and opencode installs compare bytes and demand `--force` for any recorded older release.
The redesign extends the manifest-managed admission rule to every installer-owned file,
one classifier for all of them:

| Existing destination state | Action |
|---|---|
| bytes identical to the new rendering | no-op |
| manifest-managed older release | replace, no backup |
| edited or unrecorded | refuse; name the finding |
| edited plus `--force` | replace after the exclusive `O_EXCL` backup |
| any state under `--dry-run` | print intent, write nothing |

Without this,
every `uv tool upgrade semlf && semlf install` would refuse on the skill and plugin
and turn routine upgrades into a forced-overwrite ritual.

### One implementation, two doors

The lifecycle code moves into `cli/semlf/` modules.
`scripts/install.py` remains as the checkout-side door for air-gapped and development use,
keeping its entire current flag vocabulary —
`--codex`, `--opencode`, `--agentsmd PATH`, `--cli`, `--auto`,
`--uninstall`, `--dry-run`, `--force`, and no-flag status —
as a thin parser over the same shared operations,
so `install.sh` keeps working with zero changes
and every documented checkout invocation means what it meant before.
`--auto` on the checkout door keeps installing the zipapp unconditionally;
the package door's `semlf install` never does.

### Channels after the change

| Channel | Command | Audience |
|---|---|---|
| Package (primary) | `uv tool install semlf` / `pipx install semlf`, then `semlf install` | anyone whose machine reaches PyPI or a git host |
| Package from a mirror | same, with `git+ssh://git.internal/...` or an internal index | private networks |
| Checkout | `git clone` + `python3 scripts/install.py`, or `install.sh` | air-gapped machines, development |
| Claude Code | `claude plugin marketplace add` + `claude plugin install` | unchanged |

One channel per machine stays the rule.
The collision surface moves with the redesign —
uv shim versus pipx shim versus a leftover pre-redesign zipapp —
and the quickstart's channel note plus the status/doctor migration report above are what surface it.

### PyPI

The first PyPI publish is a required step of this slice:
the README quickstart flips to `uv tool install semlf` in the same release that publishes,
never before.
Name availability on PyPI is a release gate to verify at publish time.
Publishing stays a maintainer release act —
repository automation never builds or uploads a PyPI artifact —
and the git-URL install remains fully supported as the mirror story,
so private networks lose nothing.
The agentsmd snippet's own fallback install line is updated to the new command
as part of the payload work.

### README restructure

Two tiers, in this order:

1. What it is and the diff argument (current opening, trimmed).
2. **Quickstart** — the three-line block above,
   plus the Claude Code marketplace pair,
   plus a per-agent table for readers who want exactly one integration.
3. **What gets installed** — a matrix: component × location × purpose × who needs it.
   The CLI's optionality is stated per channel, because it differs:
   on the package channel the `semlf` package is the installer and cannot be skipped,
   but its check commands remain optional;
   a guardrail-only machine with no CLI at all is the checkout door's offer
   (`install.sh --codex`, no `--cli`).
4. The layers, suppression, configuration, and git-modes sections, as today.
5. **Appendix** — air-gapped and mirror installs
   (`install.sh`, `SEMLF_REPO`, the zipapp channel), lifecycle detail, testing.

A channel-conflict note sits with the quickstart:
one channel per machine, and `semlf doctor` names a collision when it sees one.

### ADR impact

- **ADR-0014** — amended in both its decision and its rejected-alternatives list:
  payload embedding removes the "no payload to copy from" premise
  that justified rejecting the verb move,
  and install, uninstall, and status move behind `semlf`.
  Preflight-then-apply, the provenance manifest,
  structural hook ownership, and doctor's contract carry over;
  the managed-upgrade rule is extended, not weakened,
  by the state machine above.
- **ADR-0015** — amended in three places:
  wheel and zipapp contents gain the payload table's rows,
  the package channel gains PyPI as its primary source
  (with the git-URL install retained for mirrors),
  and the collision story records the moved surface.
  The maintainer-act publishing boundary and the no-fork mapping rule stand.
- **ADR-0004** — its decision text assigns the lifecycle verbs to `scripts/install.py`;
  that sentence is rewritten, not merely re-referenced.
- **`.agents/rules/100-project-map.md`** — repeats the verb assignment
  and is amended in the same commit as the ADRs.

## Non-goals

- No Node or npm channel.
  The Vercel `skills` CLI (`npx skills add`) installs skills only —
  it cannot install the hook, which is this kit's load-bearing layer —
  so at most the README mentions it as a skill-only supplement with that caveat stated.
- No change to the Claude Code install.
- No change to detector behavior, hook wire formats, or the one-file core rule.
- `semlf update` (headroom-style, channel-detecting self-update) is a possible follow-up,
  not part of this slice.

## Testing

- Byte-identity: embedded payloads match their canonical sources,
  and the wheel's payload set matches the zipapp's, member for member.
- Rendering: the installed codex hook entry and skill body are asserted against the payload table's transforms,
  from a wheel install and a zipapp install, not only the checkout.
- Migration: tests begin from current checkout-rendered artifacts
  and existing provenance records,
  then exercise package-door install, status, doctor, dry-run, force, and uninstall over them —
  including the leftover-zipapp report.
- The upgrade state machine is tested per artifact, all five rows.
- `tests/test_packaging.py` extends to pin the payload data files.

## Sequencing

This is a full slice (CLI surface, packaging, ADR amendments, README rewrite),
sized like v0.6c, with the first PyPI publish as its closing step.
Where it lands relative to the ADR-0011 gate review is a scheduling call for the owner;
nothing in it depends on the gate's outcome.
The README's component-model matrix and section reorder (tier 2 and 3 above)
could ship earlier as a docs-only change if a stopgap is wanted.
