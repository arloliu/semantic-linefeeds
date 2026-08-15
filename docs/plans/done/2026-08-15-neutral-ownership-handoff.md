# Handoff: neutral ownership for the shared skills root

**Date:** 2026-08-15
**Status:** implemented
**Predecessor:** [the setup-skill design](2026-08-15-setup-skill-design.md), shipped on `feat/setup-semlf-skill`

## Why this exists

The predecessor shipped skills per target: each agent gets its own copy, in a root it owns.
That was the right call at the time and it is verified working —
but three loose ends all resolve the same way, and none of them resolves separately.
This is the record of what a fresh session needs to pick them up.

Read the predecessor's "Why per-target rows instead of one shared destination" section first.
It states the three reasons a shared copy was rejected,
and this work has to answer all three rather than reopen them.

## The three loose ends

**1. A symlink joining two roots is refused rather than handled.**
`~/.config/opencode/skills` pointing at `~/.agents/skills` collapses two rows onto one inode.
Preflight now detects that and refuses the whole request (`colliding_destinations` in `cli/semlf/lifecycle.py`),
which is safe but blunt: it tells a user to undo their own arrangement before installing.
The shared destination is genuinely readable by both agents,
so the honest answer is one copy, which is what this work is.

**2. Two same-named judgment skills on a dual-agent machine.**
opencode scans its own skills root *and* `~/.agents/skills`,
so installing both targets offers it two skills named `semantic-linefeeds` whose bodies cite different checker paths.
Both work.
Neither is tidy.

**3. Duplication for its own sake.**
Two identical setup skills on every dual-agent machine, from one source, forever.

## What the change is

One copy of each skill at `~/.agents/skills`, owned by something that is not a single target.
opencode reads that directory natively (verified against the installed binary's own docs table, opencode 1.18.18),
so nothing needs to be written under `~/.config/opencode/skills` at all.

The opencode *command* file stays where it is and stays opencode-owned:
`~/.config/opencode/commands/setup-semlf.md` is not a skill and collides with nothing.

## The four questions it must answer

These are the predecessor's, restated with what is now known about each.

### 1. The checker and README dependency

The judgment skill is rendered with absolute paths to a checker and a README.
Codex's copy resolves the neutral root; opencode's resolves its own plugins directory.
One shared copy can only cite one of them.

Options, in the order they look promising:

- Make `checker` and `readme` neutral-owned too, so any selected target publishes them.
  opencode then carries a redundant second checker beside its plugin —
  harmless, but worth deciding deliberately rather than by accident.
- Stop citing absolute payload paths from the skill body,
  and have the skill resolve its checker at read time.
  Cleaner, but it changes what the skill tells the model to run, which is a user-visible contract.

The setup skill has no such dependency and can move first, independently.
That is worth doing as its own step: it is the whole benefit with none of this question.

### 2. Consumer inference

`installed_consumers()` in `cli/semlf/lifecycle.py` counts Codex as installed when the skill file is present.
Its docstring says why, and the reason is real:
the skill references the neutral payloads, so removing only the hook must not downgrade them to leftovers.

A shared skill breaks that inference — an opencode-only machine would report a Codex consumer,
and `doctor` would then fail it for Codex payloads nobody installed.
Codex needs a different signal.
The owned hook entry is the obvious candidate;
confirm it is sufficient before relying on it.

### 3. Last-consumer uninstall

Removal is per target today, and `plan_remove_targets` is branched by target name.
One shared file needs a rule: remove it only when no remaining target needs it.
Note the neutral root already has a version of this rule —
the checker and README are deliberately left behind when the last integration goes,
with `status` naming them for manual removal.
Match that precedent or supersede it explicitly.

### 4. Migration

A machine installed before the change has copies under `~/.config/opencode/skills`.
After it, those are orphans with live provenance records.
`semlf install` must clean them up rather than leave them,
and `tests/test_migration.py` is where that gets pinned.

## Constraints

- It changes ADR-0016's owner model, and `docs/decisions/README.md` says an accepted record is not edited.
  So it carries a new decision record superseding ADR-0016 in part,
  and it supersedes [ADR-0018](../../decisions/0018-skills-ship-per-target.md) —
  which is only a day old, and whose reasoning should be read before overturning it.
- Precision over recall applies: a refusal is acceptable, silently writing over a user's file is not.
- The registry is the one mapping.
  No consumer invents a second one.

## Where the seams are

Verified locations, so a fresh session does not have to find them again:

| Concern | Location |
|---|---|
| Owner-to-target selection | `plan_install`, `cli/semlf/lifecycle.py` — `row.recorded and row.owner in targets` |
| Collision refusal added by the predecessor | `colliding_destinations`, same file |
| Consumer inference | `installed_consumers`, same file |
| Removal, branched per target | `plan_remove_targets`, same file |
| Status's hard-coded artifact list | the literal `(name, label)` tuple loop in `status_command` |
| Destinations | `cli/semlf/manifest.py`, one helper per artifact |
| Rows | `cli/semlf/registry.py`, and `manifest.KNOWN` must match (a test couples them) |
| Skill rendering | `render_skill` / `render_codex_skill` / `render_opencode_skill` in `registry.py` |

`scripts/install.py` shares all of this through `lifecycle`.
It kept its own copy of the removal plan until this branch fixed that;
check for any similar second mapping before adding one.

## Verifying

```bash
python3 -m pytest tests/ -q          # 1166 passed at handoff
uv run ruff check .
python3 scripts/check_linefeeds.py --file <touched Markdown>
```

Two sandbox checks worth repeating, since both caught real defects:

- Install one target alone, and confirm no artifact cites a file another target owns.
- Reproduce the symlink (`ln -s $HOME/.agents/skills $XDG_CONFIG_HOME/opencode/skills`),
  install both targets, and confirm nothing is half-written.

The live check that testing cannot replace:
install from the checkout, then ask a real Codex and a real opencode to load the skill and quote a rule back.
Both were verified this way on 2026-08-15.

## Not in scope

- Changing what the hook reports, or any detector behavior.
- The opencode command file, which is settled.
- Claude Code, which the marketplace owns and `semlf` never touches.
