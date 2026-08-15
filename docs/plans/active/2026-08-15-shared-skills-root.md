# One skill, one copy, in the root both targets already read

**Date:** 2026-08-15
**Status:** in review — revised after two rounds of external review, no code written yet
**Answers:** [the neutral-ownership handoff](2026-08-15-neutral-ownership-handoff.md)
**Supersedes:** [ADR-0018](../../decisions/0018-skills-ship-per-target.md), whose objections are answered at the end

## What this changes

A skill is published **once**, to `~/.agents/skills`.
Both targets read that directory natively, so nothing is written under `~/.config/opencode/skills` at all.

Today a skill ships once per target.
`semlf install codex opencode` writes two `semantic-linefeeds` skills and two `setup-semlf` skills,
whose bodies differ in which checker path they cite.
On a machine where the two roots are joined by a symlink, install refuses the whole request instead.

## Why the current shape breaks

Three problems, and they share one cause.

**A user's symlink turns a working install into a refusal.**
`~/.config/opencode/skills` pointing at `~/.agents/skills` collapses two rows onto one inode.
`colliding_destinations` detects that and refuses,
which is safe but tells a user to undo their own arrangement before installing.
The arrangement is not exotic:
it is what a developer running several agents does so that one skill store serves all of them,
and it is what `mattpocock/skills` produces automatically —
that tool installs into `~/.agents/skills` and symlinks each skill directory into every agent's own root.

**A copy in opencode's own root can shadow the shared one.**
Measured, not assumed (see the findings below).
A machine that installed opencode's skill under the old layout,
and then upgrades to a layout that publishes only the shared copy,
can keep loading last release's skill.

**Duplication with nothing to show for it.**
Two identical setup skills on every dual-agent machine, from one source, indefinitely.

This design fixes all three by removing the second destination rather than by managing it.
There is one skill row, so two rows cannot collide,
whatever the user has symlinked to whatever.

## Verified findings

Each was checked on 2026-08-15 against the installed binary or the source, and each one shaped the design.

### opencode reads the shared root, and reports one skill per name

`opencode debug skill` lists every skill opencode resolves, as JSON.
On a machine whose `~/.config/opencode/skills` is a symlink to `~/.agents/skills`,
it reports 30 skills and **no duplicate names**,
so a skill reachable by two paths is advertised once.

Precedence was measured in isolation rather than inferred from that machine, where both roots are one inode.
With a distinct `ztest` skill placed in each of two separate roots,
opencode reports exactly one, and it is the copy under its own root.

That is what makes a stale copy in opencode's own root dangerous,
and it is why migration must remove those files rather than merely stop writing them.

The design's load-bearing assumption was then tested on its own:
with no opencode skills directory present at all,
`opencode debug skill` still resolves the skill from `~/.agents/skills` and reports that path.
The scan is unconditional rather than opted into, and `skills.paths` only appends to it.

Two opt-outs are acknowledged rather than claimed away.

`OPENCODE_DISABLE_EXTERNAL_SKILLS` turns off the external scan itself,
which is the one setting that makes the shared copy unreachable while everything else looks healthy.
It produces exactly the silent failure the version floor guards against,
so it is named in the README beside that floor rather than left to be discovered.
`OPENCODE_DISABLE_PROJECT_CONFIG` does the same for project-level directories.

Separately, a per-agent configuration can disable the `skill` tool, or disable an individual skill,
and that hides the shared copy wherever it lives.
Both are choices a user makes, not gaps in this design.

### Precedence is a race, and it covers only the global roots

"Own root wins" is an observed outcome, not a rule opencode publishes.
Every discovered match is added with unbounded concurrency into a name-keyed store, so the last add to complete wins,
and config directories are scanned after external ones, which is why their adds tend to land last.
Rather than documenting a precedence,
opencode's own troubleshooting page tells users to keep skill names unique across locations.

The claim also holds only for the global roots.
Effective order puts a project-level `.opencode/skill` or `.opencode/skills` above every global root,
so a project-level copy outranks the shared one, and nothing in this design looks there.
That is a stated carve-out rather than a case this design handles,
and it is the same blind spot `_judgment_layer_present` already has.

Nothing here depends on the distinction.
Whether a stale copy shadows the shared one deterministically or by winning a race, it is a hazard,
and removing it is the answer either way.

### Writing nothing to opencode's own root also costs nothing

opencode does not silently deduplicate.
The name-keyed record is overwritten,
and `duplicate skill name` is logged each time the same name arrives from another path.
Measured on this machine:
2586 such warnings across 53 runs, between 30 and 57 per run.

Those are the user's own arrangement, not semlf's —
this machine's opencode skills root is a symlink to the shared root,
so every skill there is discovered twice by two spellings, and most belong to another tool.

An earlier draft of this design installed a symlink in each agent's own root, pointing at the shared copy.
That would have added one such warning per linked skill at every process start,
on any machine whose roots are not already joined.
It is dropped.
The reason it existed was to occupy the slot that wins,
and precedence turns out to be a race between two paths that resolve to the same bytes,
so the slot is not worth owning.
`doctor` still watches that slot for a file that would shadow the shared copy,
which is the protection that mattered, and it needs no artifact of ours to sit there.

### `mattpocock/skills` does not prune the shared root

Under this design `~/.agents/skills` holds the only copy of both skills,
and that directory is also managed by `mattpocock/skills` through `~/.agents/.skill-lock.json`.
A tool that reconciled that directory against its own lock would delete semlf's artifacts.

Version 1.5.15's bundle was read to settle this.
Every removal it performs is one of:
temp-directory management, the canonical directory it is itself about to write,
the link path inside `createSymlink`, a flat-file install for one specific agent,
and two sites reached only by an explicit `skills remove`.
Nothing enumerates the directory looking for entries absent from the lock.
The shared copies are therefore safe from another tool's sync.

The remaining exposure is a name collision:
that tool's own canonical write lands over ours
when a user runs `skills add` for something named `semantic-linefeeds` or `setup-semlf`.
That is user-initiated and out of this design's reach;
`semlf doctor` reports the resulting mismatch, which is the right outcome.

### The hook's judgment-layer probe needs no change

`_judgment_layer_present` in `scripts/check_linefeeds.py` already probes `$HOME/.agents/skills/semantic-linefeeds/SKILL.md`,
which is the shared destination.
Its opencode candidate keeps working too:
`_looks_like_the_skill` opens candidates with `open()`, which follows symlinks,
so a joined root answers `True` through the user's own arrangement.
On a machine with separate roots that candidate simply stops matching, and the shared one carries the answer.
No detector behavior changes.

### `opencode-readme` has no consumer other than the opencode skill

Nothing under `adapters/opencode/` references a README.
That row exists only so the opencode skill's suppression link resolves offline.
Once one shared skill cites the neutral README, the row is an orphan.

### The opencode plugin genuinely needs its own checker

`adapters/opencode/semantic-linefeeds.ts:76` resolves `./check_linefeeds.py` through `import.meta.url`,
so the copy beside the plugin is load-bearing and stays.
A dual-agent machine therefore carries two checkers.

### Two paths are the same file, and `realpath` cannot always tell

Several rules below turn on one question:
does this path and that path name the same file?

`os.path.realpath` answers it for symlinks and it is what the current collision check uses,
but it does not resolve a bind mount.
A user who joins two roots with `mount --bind` gets two different real paths for one inode.
Every guard keyed on realpath would then read "different file", admit a removal, and unlink the shared copy.

So the rule throughout is:

- **`os.path.samefile`, or `st_dev` and `st_ino` compared directly, whenever both paths exist.**
  It is correct through symlinks, bind mounts, and hard links alike.
  It raises when either side is missing, so every caller handles that rather than letting it propagate.
- **When a path does not exist yet, the comparison climbs to what does.**
  A path that has never been created has no inode, so `samefile` cannot answer for it directly.
  `realpath` alone is not the answer either.
  On a fresh machine whose `~/.config/opencode/plugins` is bind-mounted onto the payload root,
  neither checker destination exists,
  `realpath` reports two different paths, no collision is detected,
  and the request half-applies:
  the first write creates the file and the second fails as "appeared after classification".

  So each side is reduced to its **nearest existing ancestor plus the unresolved suffix below it**.
  Two paths are the same destination when those ancestors are `samefile`
  and the suffixes are equal.
  That answers correctly for a bind mount, a symlinked parent, and an ordinary distinct path alike,
  and it degrades to a plain comparison when both leaves already exist.

  The suffixes are compared as exact strings, and that has a stated limit rather than a guarantee.

  A suffix only ever holds components below the deepest directory that exists,
  and those come from this project's own registry literals.
  Everything a user can spell differently — `$HOME`, `XDG_CONFIG_HOME`, a differently-cased path —
  sits at or above the anchor.
  There `samefile` resolves it against the filesystem's own rules rather than by string comparison.

  What that does **not** cover is two components that do not exist yet
  and differ only by case, or only by Unicode normalization,
  on a filesystem that treats them as one name.
  Creating either would create the other, so they are one destination and this test calls them two.
  No pair of rows can reach it today:
  the suffixes below any shared anchor differ by literal name — `semlf` against `opencode`,
  `skills` against `plugins` — never by case alone.
  It is written down because that is a property of the current row set rather than of the rule,
  and a future row whose destination differed from another's only in case would need this revisited.

`colliding_destinations` is where both halves meet:
it compares destinations that may not exist, and, since it now also compares against installed rows,
destinations that do.

### Where a dangling symlink defeats the comparison, and why nothing is lost

Two cases exist, both real, and neither ends in a lost file.

A destination that is itself a dangling symlink does not compare equal even to itself:
`lexists` says the path is there, `samefile` follows the link, and `stat` raises on the missing target.
So the collision goes undetected.
It does not matter, because the object-state axis refuses that destination before anything is written —
`classify_artifact` reports "is a symlink" and says `--force` never overrides it.
The request refuses instead of colliding.

A dangling symlink partway down one path's uncreated portion is the other case.
`lexists` stops the walk on the link itself, so that side's anchor sits deeper than the other's,
the suffixes differ in length, and the comparison says "different".
Creating the missing directory later would make both paths one file.
This ends in an ordinary apply error rather than an overwrite:
publishing creates the destination's parent first, and `mkdir` on a dangling symlink raises,
so the row fails loudly and `apply_plan` reports exactly what was and was not applied.

Both are recorded rather than fixed.
Detecting them would mean resolving paths that deliberately have no resolution,
and the outcomes — a refusal and a named error — are the two this project already treats as acceptable.

### The removal guard compares parent directories, not files

Asking "is the legacy path the same file as the shared destination" is the wrong question,
even though it is the obvious one.

The right question is whether unlinking the legacy path would destroy the shared file's own directory entry.
That is answered by the **parents**:

- `samefile(dirname(legacy), dirname(shared))` — the two roots are joined,
  by a parent symlink or a bind mount, so `os.unlink` on the legacy path resolves to the shared entry.
  Skip the removal.
- the parents differ — the legacy path is a hard link or a leaf symlink to the shared file,
  and unlinking it removes only that entry.
  Remove it.

Comparing the files instead gets the second case backwards, and that is not a tidiness problem.
A hard link left in place survives exactly until the shared file is next published.
`publish_bytes` stages a temporary file and `os.replace`s it, which gives the shared path a new inode,
and the hard link is then stranded on the old content —
a stale copy in opencode's own root serving last release's instructions,
which is the failure this whole design exists to prevent.

A leaf symlink is the milder version of the same case.
It tracks the shared file across a republish rather than going stale, so leaving it is harmless,
but it is legacy residue and removing it is safe.
`plan_remove_file` refuses a non-regular destination, so a symlink there is reported rather than unlinked,
which is an acceptable outcome and not a silent one.

### What absence means, for each guard that asks

`samefile` raises when either side is missing, and the fallback is not the same everywhere.
Getting one backwards either strands a file forever or deletes the shared copy.

| Guard | Missing side | Conclusion |
|---|---|---|
| legacy removal, and migration | the shared destination does not exist | **admit the removal** — nothing can be destroyed through a path that is not there, and refusing would strand the legacy artifact permanently |
| legacy removal, and migration | the legacy path does not exist | **admit** — there is nothing to unlink, and admitting is what lets the stale record be cleared |
| `doctor`'s competitor check | the opencode path does not exist | healthy, and silent |
| `doctor`'s competitor check | the shared file does not exist | report that install has not run under this layout, not that something is shadowed |
| `colliding_destinations` | either destination does not exist | compare nearest existing ancestors with `samefile`, and require the unresolved suffixes to be equal |

Two properties of `samefile` are worth naming rather than discovering later.
It goes through `os.stat`, so it **follows symlinks** —
the opposite of `read_regular_bytes`, which carries `O_NOFOLLOW` on purpose.
Following is right here, because the question is "are these one file" rather than "may I read this path safely",
but the difference is deliberate on both sides and neither primitive should drift toward the other.
And it raises when either path is missing.
So every caller states what absence means for its own question, instead of letting the exception escape.

### Provenance identity keeps its own test, and that is stated rather than unified

`manifest.classify_entry` already answers a version of the same-file question,
comparing a queried path against a recorded one with `realpath` (`manifest.py:210`),
and `doctor` uses the same comparison to explain *why* an entry reads as unrecorded (`doctor.py:204`).
This design does not change them.

So the repository ends with two tests for one-looking question, and that is intentional.
They answer different questions:
`classify_entry` asks whether a record describes the path in front of it, and fails closed to `unrecorded`;
the new guards ask whether a removal would destroy the shared copy, and fail closed to retaining it.

They can disagree only where a bind mount joins two spellings of one file.
There, `classify_entry` reads `unrecorded` and install refuses without `--force`,
while a guard reads "same file" and declines to delete.
Both refuse to destroy anything, which is the direction that matters,
so unifying them would widen this change into ADR-0014's core for no safety gain.
A reader who notices the asymmetry should find this paragraph rather than a silence.

### Removal of a file refuses anything that is not a regular file

`plan_remove_file` refuses a directory and refuses a non-regular file (`lifecycle.py:988-1000`).
That function also unlinks its destination unconditionally once `--force` admits it.
On a machine whose opencode skills root is joined to the shared root,
the legacy opencode skill path is the shared file,
so a forced removal would delete it through the parent symlink.
Today that is unreachable, because install refuses on such a machine before anything is written.
This design makes such machines installable, so it must not re-open that door.

## The four questions the handoff left open

### 1. The checker and README dependency

One shared body can cite only one checker path, and only one README.

**Decision: `checker` and `readme` become shared rows**, published when any agent target is selected.
The shared skill cites `~/.local/share/semlf/`, and that root now exists for an opencode-only install too.

The alternative was to stop citing absolute paths and have the skill resolve its checker at read time.
It is rejected because the citation is not accidental.
`semlf_data_dir()` states the reason it exists:
installed hooks and skills point at the neutral root whatever channel `semlf` itself arrived by,
so a hook survives a channel switch, a virtual-environment rebuild, or a CLI uninstall untouched.
A skill that calls `semlf check` first depends on the CLI being on `PATH`,
which is the one thing the neutral root was chosen to avoid depending on.
The cost also lands in the wrong place:
a read-time fallback is prose instructing a model, untestable from pytest and visible to users,
while a shared row is a registry field with types and tests behind it.

A variant was considered and rejected:
publish the checker inside the skill directory and cite it relatively.
The Codex hook still needs the copy under the data root,
so a dual-agent machine would carry three checkers instead of two.

This decision has a consequence worth stating plainly, because it is new.
An opencode-only machine previously created no neutral data root at all.
It now does, and after `semlf uninstall opencode` that machine retains a checker and a README —
about 112K on a machine class that used to uninstall to nothing.
`semlf status` names them for manual removal, as it already does for every other retained shared payload.

### 2. Consumer inference, and the two questions it now has to answer

`installed_consumers()` counts Codex as installed when its skill file is present.
Its docstring gives the reason:
the skill references the neutral checker and README,
so removing only the hook must not downgrade those payloads to leftovers.

Making them shared rows dissolves that reason.
They are no longer Codex's, and their consumer is any installed integration.

**Decision: `installed_consumers()` infers Codex from its owned hook entry alone**, and opencode from its plugin file.
That stops an opencode-only machine from inventing a Codex consumer,
which was ADR-0018's second objection to a shared root.

That predicate must not also decide removals.
It was built for reporting, where a false "absent" costs a harmless leftover warning,
and it fails closed on every kind of trouble:
`read_state_json` returns `None` for an unreadable, oversized, malformed, or badly encoded `hooks.json`,
and a hand-edited `hooks.json` is exactly the state a user is in when they reach for uninstall.
Promoting it to a deletion predicate would turn each of those into data loss.

**A second, deliberately conservative predicate decides whether a shared skill may be removed.**
It answers "does this target still have artifacts on this machine",
and every ambiguity resolves to *yes*.
`plan_remove_codex_hook` already draws that line for the hook itself (`lifecycle.py:1067`),
and this is the same discipline applied to the question that now authorises a delete.

"Ambiguity resolves to yes" is a principle, not an algorithm, and stated alone it is not enough.
The predicate must also say **which places it looks**.
A place it never examined is not the same as a place it found empty.
The reporting predicate probes only destinations derived from the current environment (`lifecycle.py:731-750`),
so a machine that installed opencode under one `XDG_CONFIG_HOME`
and runs `uninstall codex` under another would report opencode absent
and delete shared skills that a live opencode installation still uses.

The algorithm is therefore:

1. Probe every target-owned destination derived from the current environment,
   with a **tri-state** result — present, absent, or could-not-inspect — never a boolean.
2. Read every valid target-owned entry in the one manifest snapshot,
   and probe the path each entry records, which may differ from the current environment's.
3. A target counts as **present** when any of its current or recorded paths proves readable bytes,
   and equally when any of them is could-not-inspect.
4. A target counts as **absent** only when every one of its paths was examined and proven missing.
5. A record whose file is proven gone is a stale record, not evidence of presence.
   It counts as absent, and it is forgotten when that target is named in the request.

The fifth rule is what stops the opposite failure.
`plan_remove_file` reports a vanished destination as "not installed" and leaves its record in place
(`lifecycle.py:976-982`),
so a machine the user had cleaned up by hand would retain the shared skills forever
if every valid record counted as permanent presence.

### 3. Last-consumer uninstall

**Decision: the two shared skills are removed only when this request covers every target that still has artifacts.**
`checker` and `readme` keep the retain-and-report precedent.

Stated as a rule:
a shared skill is removed when, for every agent target, either the target is named in this removal request
or the conservative predicate above finds no artifacts for it.
Anything else retains the skills and names them in `status`.

Sequential uninstalls still converge.
`uninstall codex` while opencode is installed retains the skills;
the later `uninstall opencode` finds Codex artifact-free and removes them.

One consequence is accepted rather than designed away.
The shared skill is lost by a user who hand-deletes the Codex hook and then runs `uninstall opencode`,
because Codex genuinely has no artifacts left at that moment.
The alternative — treating a skill's presence as evidence of a consumer — is the inference removed above,
and it is what makes an opencode-only machine report a Codex consumer.
The two cannot both hold.
Retaining on ambiguity covers the cases where the evidence is merely unreadable,
which is the failure mode that loses data silently;
this one requires the user to have deleted their own hook first, and `status` reports the result.

**Removals of shared skills are planned last.**
`apply_plan` stops at the first `OSError` and returns 1,
so a shared removal placed early would strand a target with its own artifacts installed and the skill gone.
Planned last, the same failure leaves the shared skills intact and a re-run converges.
This ordering does not come from the registry's `order` field, which describes publication;
it is a property of the removal plan and is stated here because that is where a reader will look for it.

The asymmetry against `checker` and `readme` is deliberate and it is about behavior, not tidiness.
A checker left behind does nothing until something calls it.
A skill left behind is still advertised to every model that scans the root,
and the checker path in its body may by then point at nothing.

### 4. Migration

Covered in its own section below.

## The registry

`owner` gains one value, `shared`:
the row publishes when **any** agent target is selected, and never for `agentsmd` alone.

| id | owner | destination |
|---|---|---|
| `checker` | `shared` (was `codex`) | `~/.local/share/semlf/check_linefeeds.py` |
| `readme` | `shared` (was `codex`) | `~/.local/share/semlf/README.md` |
| `skill` (was `codex-skill`) | `shared` (was `codex`) | `~/.agents/skills/semantic-linefeeds/SKILL.md` |
| `setup-skill` (was `codex-setup-skill`) | `shared` (was `codex`) | `~/.agents/skills/setup-semlf/SKILL.md` |
| `codex-hook-template` | `codex` | `$CODEX_HOME/hooks.json` |
| `opencode-plugin` | `opencode` | `…/opencode/plugins/semantic-linefeeds.ts` |
| `opencode-checker` | `opencode` | `…/opencode/plugins/check_linefeeds.py` |
| `opencode-setup-command` | `opencode` | `…/opencode/commands/setup-semlf.md` |
| `agentsmd-snippet` | `agentsmd` | user-named |

Rows removed: `opencode-skill` and `opencode-setup-skill`, replaced by the shared copy;
`opencode-readme`, which has no consumer left.

Every row still describes a payload with a source, a member, and a rendering,
so `registry.stage_payloads`, the zipapp builder, the wheel build hook,
and the packaging tests that assert each row's member is present all keep working by construction.
Row renames alone are carried by those paths automatically.

`opencode-checker` stays for the reason in the findings,
and teaching the plugin to read the neutral checker is not part of this work.

Skill rendering collapses to one function.
`render_codex_skill` and `render_opencode_skill` become a single renderer pinned to the neutral root,
and the two `_replace_exactly_once` transforms keep their fail-loud behavior unchanged.

### Every place that reads `row.owner`

Widening the owner is not one edit.
The comparisons that must learn about `shared` are:

- `plan_install` (`lifecycle.py:626`), the selection this design is built on.
- **`colliding_destinations` (`lifecycle.py:595`)**, which uses the same `row.owner in targets` test.
  A `shared` row is in neither target set, so without this the shared checker drops out of collision detection —
  and the section below that promises `checker` against `opencode-checker` is still refused would be false.
- `status_command`'s missing-and-leftover comparisons (`lifecycle.py:861`, `lifecycle.py:869`).
- `doctor._payload_identity_check`'s expectedness test (`doctor.py:234`).

For a `shared` row the expectedness question becomes `bool(consumers)` rather than membership:
any installed integration makes a shared payload expected,
and only a machine with no integrations at all reports one as a leftover.

The registry's owner-map test (`tests/test_registry.py:40-55`) pins the current mapping and changes with it.

## The collision refusal

`colliding_destinations` keeps its purpose but not its selection test, which is covered above.

The collision it was originally written for stops existing:
there is one skill row, and one row cannot collide with itself.
That is the whole answer to arbitrary symlink topologies —
not a smarter refusal, and not a rule about any particular arrangement.
Every arrangement leads to the same single destination:
a root symlink, a per-skill leaf symlink, an intermediate symlink, or a shared root that is itself a symlink.

What the check still covers is `checker` against `opencode-checker`,
joined when someone points the plugins directory at the data root.
That still deserves a refusal:
the bytes match, but two provenance records would name one file,
and `uninstall opencode` would delete the copy the other integration depends on.

### It must also compare against what is already installed

Fixing the owner test is necessary and not sufficient.
`colliding_destinations` compares only the rows **this request selects**,
so a collision assembled across two separate requests is invisible to it.

The reachable sequence is three ordinary steps:

1. `semlf install codex`, which publishes `checker` and `readme` under the data root.
2. Point opencode's plugins directory at that data root.
3. `semlf install opencode`, a request that selects no shared row for comparison.

Step 3 finds bytes that already match its own rendering.
`checker` and `opencode-checker` carry the same canonical source, as do `readme` and `opencode-readme`,
so it adopts them and writes a second provenance record naming the same file.
Nothing refuses, because the row it would have collided with was not in the request.

From there every removal path deletes a file another integration depends on.
`uninstall opencode` unlinks `opencode-checker`'s destination,
migration unlinks a proven `opencode-readme`,
and both are the shared copies a surviving Codex hook still points at.

So the comparison widens on both axes:

- **Every selected destination is compared against every other selected destination**, as today.
- **And against every already-installed destination that a valid record proves**,
  whether or not its row is part of this request.
- The same-file guard extends to those pairs:
  `opencode-checker` against `checker`, and a retired `opencode-readme` against `readme`.
  When two names resolve to one file, the file is preserved and only the redundant record is cleared.

This is a pre-existing hole rather than one this design opens —
the current check has always been request-scoped.
It becomes reachable here because shared rows make the data root exist on machines that never had one.

## Install

Selection becomes:

- `row.owner in targets` for the target-owned rows, unchanged.
- `row.owner == "shared"` when at least one agent target is selected.

`agentsmd` alone selects no shared row.
It is a paragraph of text with no checker and no skill behind it.

## Uninstall

Per-target removal keeps its shape, with two additions.

**Last consumer**, by the conservative rule stated earlier, with those removals planned last.

**Legacy rows.**
Uninstall must remove the pre-change artifacts too, not only the new ones.
Upgrading the package and immediately running `semlf uninstall opencode` is a reachable path,
and it never runs an install under the new layout.
Without this, the old judgment skill, the old setup skill, and the plugin README survive an uninstall that reported success,
and a stale skill in opencode's own root stays advertised.
The converse holds for Codex:
a legacy skill proven only by a `codex-skill` record must not refuse removal because the new plan asks for `skill`.
`tests/test_migration.py` already pins direct uninstall of an old recorded skill, and that contract is kept.

Removing a legacy opencode skill carries the same guard migration does, for the same reason:
on a joined root that path is the shared file, and `plan_remove_file` under `--force` would unlink it.
A legacy removal is admissible only when it is not the same file as the shared destination.

**That guard cannot be expressed as an admission verdict.**
`plan_remove_file` reaches its unlink through `if not (admit or force)` (`lifecycle.py:1025`),
so a guard that merely withholds admission is overridden by `--force` and the unlink runs anyway.
It belongs either in `plan_remove_targets`, so `plan_remove_file` is never called for that artifact,
or as a refusal inside it that ignores `force` entirely.
The precedent is `classify_artifact`,
where a non-regular destination is refused with "`--force` never overrides this" (`classify.py:62-68`):
the object axis is decided before provenance is consulted, and force widens only the provenance axis.

When that guard refuses the unlink, **the retired record is kept, not forgotten.**
Forgetting it is what a successful removal does, and this removal did not happen.
On a joined root with another consumer still installed —
upgrade the package, then `uninstall opencode` while Codex remains —
the shared file survives correctly, but its only proof is that retired record.
Forgetting it would leave a file no record proves, whose bytes differ from the new rendering by construction,
so the next `semlf install codex` would refuse without `--force`:
a dead end reached by ordinary steps on the exact topology this design exists to support.
The record is instead projected onto `skill` or `setup-skill`, the same treatment migration gives it.

`checker` and `readme` are retained and named by `status`, as they are today.
The closing note about retained shared payloads now prints whenever any were retained, not only for `codex`,
and it must print from **both** doors —
`scripts/install.py`'s uninstall returns straight from `apply_plan` today and has no such note.

## Migration

Everything below is planned and disclosed like any other work.
It appears in `--dry-run` output; none of it is a silent side effect of install.

### Reaching the legacy records at all

`manifest.load`, `artifact_state_path`, and `forget` all reject a name outside `KNOWN`,
and the coupling test requires `KNOWN` to equal the recorded registry rows plus `cli`.
Once the old ids leave the registry, the normal API can neither read nor clear them.

So the retired names — `codex-skill`, `opencode-skill`, `codex-setup-skill`, `opencode-setup-skill`, `opencode-readme` —
are declared explicitly as a retired set that the state accessors admit for reading and forgetting,
while the coupling test keeps its equality against the live rows.

### Classification reads the legacy record; only apply rewrites it

`plan_install` takes one manifest snapshot and classifies against it,
and preflight is read-only so that `--dry-run` describes exactly what apply would do.
A record rename performed during planning would break that;
performed at apply time it would be too late to affect the classification that already happened.

So the snapshot handed to classification is **projected**:
when a new row has no record of its own,
and a retired record proves the same file as the new row's destination,
the projection presents that record under the new name.
Classification then sees a managed artifact and plans a normal replace,
`--dry-run` describes it truthfully,
and apply writes the new record and forgets the retired one.

A new row can have **more than one** retired alias.
On a joined root both `codex-skill` and `opencode-skill` record the same file,
so "project the retired record" is ambiguous as written.
Migration therefore collects **every** retired record that proves the new row's file, and then:

- projects one of them when they agree, since they prove the same bytes at the same file;
- refuses, naming both, when two proofs disagree about the digest of one file,
  because guessing which is authoritative is exactly the guess this project does not make;
- forgets **all** redundant retired names, and only after the new record is established.

That ordering matters for the partial states below.
A retired record cleared before the new one is written leaves a file with no proof at all.

Without this, an ordinary upgrade stops at a wall.
`classify_artifact` adopts only when the bytes already equal the rendering,
so a machine whose `SKILL.md` is unchanged would survive anyway;
a release that changed `SKILL.md` would classify the file as unrecorded and refuse without `--force`.
That case is not hypothetical on a joined root:
the shared path there may hold the **opencode** rendering, which cites the plugins directory,
so its bytes differ from the shared rendering by construction.

### What migration does to each pre-change state

| Pre-change state | Action |
|---|---|
| `~/.agents/skills/…/SKILL.md` recorded as `codex-skill` | project the record onto `skill`, publish normally, then forget the retired record |
| the same, recorded as `codex-setup-skill` | the same, onto `setup-skill` |
| a real `…/opencode/skills/…/SKILL.md` whose record proves it, whose parent directory is **not** the shared file's parent | remove it, prune its now-empty directory, forget the record |
| the same, but whose parent directory **is** the shared file's parent | project the record onto `skill` or `setup-skill`; never remove the file |
| `…/opencode/plugins/README.md` whose record proves it, and which is **not** the `readme` destination | remove it, forget the record |
| the same, but which **is** the `readme` destination | keep the file, clear only the redundant record |
| any of those paths holding content no record proves | refuse, naming the path |

The comparison is `os.path.samefile` on the two **parent directories**, for the reasons in the findings:
a bind mount joins two paths that `realpath` still reports as different,
and comparing the files themselves would spare a hard link that must be removed.

The second row is the trap this whole design has to survive.
On a machine whose opencode skills root is a symlink into `~/.agents/skills`,
the old `opencode-skill` record's path is the shared file itself.
A migration that removes whatever provenance proves is ours would delete the shared copy.
So the condition is provable **and** not the shared file,
and the record is carried forward rather than merely forgotten.

The third row prunes the emptied directory.
The old layout created `…/opencode/skills/semantic-linefeeds/` as a real directory holding `SKILL.md`,
and leaving an empty directory behind in another agent's config is untidy rather than harmful,
so the prune is the same one-level, only-when-empty prune `plan_remove_file` already performs.

### Ordering, and the states that have no rollback

Publication of the shared file and its new record comes **before** any destructive legacy cleanup.
`apply_plan` has no rollback: it stops at the first error and reports what was and was not applied,
so the only safe order is the one where an interruption leaves the shared copy present.

These partial states are reachable and each must converge on a re-run rather than refuse:

- a retired record exists but its destination is gone;
- the legacy file is gone but clearing its record failed;
- both a retired and a new record exist;
- a new record exists while one or more retired ones remain;
- two retired records name one file;
- the legacy file was removed before the shared publication succeeded;
- a guard refused the legacy removal, so its record is deliberately still there.

### `--force` on a legacy skill

Today a legacy `SKILL.md` whose record is missing or corrupt can be repaired in place:
`classify_artifact` backs it up and replaces it under `--force`.
Under this design that file is not replaced, it is removed,
and a removal whose provenance cannot be proven is refused rather than forced.

That is the intended precision trade, and it is user-visible,
so it is stated here rather than left under an out-of-scope claim that install's force behavior is unchanged.
`--force` still widens which provenance states are admissible;
what it never does is authorise unlinking a path that resolves into the shared destination.

## Status and doctor

The literal `(name, label)` loop `status_command` walks gains `skill` and `setup-skill`,
and loses the removed rows.

`doctor` gains one check it does not have today:
**a file at opencode's own skill path that is not the shared file competes with it, and is reported.**
This is the state that makes opencode load last release's skill,
and it is invisible to every check `doctor` currently runs.
It needs no artifact of ours at that path — it is an inspection, not an ownership claim.

Four things pin its semantics, because each of them is a way to get it wrong.

**It compares two specific paths; it does not enumerate a directory.**
The question is whether `…/opencode/skills/<name>/SKILL.md` is the shared file,
answered with `samefile`.
Enumerating the skills root and failing on whatever is there would fail every joined-root machine outright,
since that root is full of the shared skills by construction, plus every other tool's.

**Resolving to the shared file is healthy and silent.**
Each of these means the same file, and `samefile` says so:
a root symlink, a leaf symlink, an intermediate symlink, a bind mount, or a hard link.
The ordinary shared-payload identity check still reports stale or edited bytes there;
this check has nothing to add.

**Identical bytes are a warning, differing bytes are a failure.**
A separate file whose bytes equal the shared rendering competes for the name but serves the same content,
so it is residue for migration to clear rather than a broken machine.
A separate file whose bytes differ is what makes opencode answer with the wrong skill.

**When the shared file does not exist, the report says so instead of saying "shadow".**
On a machine that has a legacy copy and has not migrated yet, nothing is being shadowed;
the finding is that install has not run under this layout, and the message points there.

"Competes" rather than "shadows" is deliberate.
Precedence is a race, so a second copy usually wins but is not guaranteed to,
and a message promising determinism would be describing a rule opencode does not publish.

Shared payload expectedness in both verbs changes as described in the registry section.

## Testing

Pinned by the suite:

- Both topologies, each with both targets and with one target alone:
  a root-directory symlink, and a per-skill leaf symlink.
  Neither produces a refusal, and both leave exactly one skill file.
- A shared root that is itself a symlink.
- Sequential installs — `install codex` today, `install opencode` tomorrow.
  Every existing case installs both in one command,
  so the path where the second install meets the first one's files has no coverage.
- An opencode-only install now **does** create the neutral root,
  which inverts the assertion at `tests/test_semlf_install.py:160`,
  and the checker the installed skill cites is present.
- Removing one target leaves the other's install whole;
  removing the last one takes the shared skills and retains the checker and README.
- The conservative removal predicate, one case per rule:
  an unreadable `hooks.json` retains;
  a target installed under a different `XDG_CONFIG_HOME` or `CODEX_HOME` retains,
  because its recorded path still proves readable bytes;
  a record whose file is proven gone counts as absent and is forgotten rather than retaining forever.
- A collision assembled across two requests:
  install codex, join the plugins directory to the data root, install opencode.
  The second install refuses rather than adopting the shared checker under a second name,
  and neither door's uninstall deletes a file the other integration still records.
- A bind-mounted join, where `realpath` reports two different paths for one file.
  Nothing is deleted through the second spelling, and the collision is still refused.
- A legacy path that is a **hard link** to the shared file:
  it is removed, not spared, and a following republish leaves no stale copy behind.
- A legacy path that is a leaf symlink to the shared file:
  reported rather than silently unlinked, and never followed into the shared file.
- Each row of the absence table:
  a legacy removal with no shared destination yet admits rather than stranding the file,
  and `doctor` stays silent when the opencode path is absent.
- `uninstall opencode` on a joined root deletes nothing through the legacy opencode path, with and without `--force`.
- Uninstall of a legacy machine that never ran an install under the new layout.
- Migration from the pre-change layout, in both the separate-roots and joined-root variants,
  including the joined-root machine whose shared file holds the old opencode rendering.
- Upgrade then `uninstall opencode` on a joined root with Codex still installed:
  the shared file survives, its retired record is projected rather than forgotten,
  and a following `semlf install codex` succeeds without `--force`.
- Each partial migration state converges on a re-run, including two retired records naming one file.
- `doctor`'s four cases: quiet on a joined root and on a leaf symlink,
  quiet on an empty or absent opencode skills root,
  a warning for a separate file with identical bytes,
  and a failure for a separate file with differing bytes.
- The registry coupling tests, covering ids, owners, members, and the unrecorded and identity sets.

Not reachable from pytest, and verified by running the real agents:
installing from the checkout and asking a real Codex and a real opencode to load the skill and quote a rule back.
opencode reads its skills into memory at start and never retracts one,
so that check is made **after restarting opencode**;
a run that was already alive keeps serving whatever it loaded, including a file migration has since deleted.

## Records and documentation

- **ADR-0019** supersedes ADR-0018 and answers its objections.
- It amends [ADR-0016](../../decisions/0016-one-entry-point-and-the-payload-registry.md):
  `owner` may be `shared`, meaning any selected agent target.
- The README section listing install destinations is updated.
- **`adapters/opencode/INSTALL.md:23-24` tells a manual installer to copy the skill into `~/.config/opencode/skills/`** —
  the state `doctor` now reports and migration deletes.
  It is rewritten to name `~/.agents/skills`, and its claim that the skill is already visible
  when the Claude plugin is installed is revisited at the same time.
- The minimum opencode version is stated in the README and that INSTALL.md.
  ADR-0018's shape worked on every opencode because it wrote into opencode's own root;
  this one depends on opencode scanning `~/.agents/skills`, verified at 1.18.18,
  and an older opencode would lose the skill with no error at all.
  `doctor` does not probe for it by running `opencode debug skill`:
  `detect_agents` holds that detection is a presence probe and never an execution,
  and shelling into another agent's binary from a health check would break that rule for a version string.
- `scripts/install.py`'s help text still describes Codex as the owner of the skill, checker, and README,
  and still exports `codex_skill_dest` for compatibility; both are updated.
- The CHANGELOG entry is written in user-facing language,
  with no slice names, no process talk, and no bare ADR codes.

## Answering ADR-0018

That record is one day old and rejected this shape for three reasons.
Each is answered by something that has changed, not waved away.

**"It installs a skill that references files the install never wrote."**
True while the checker and README were Codex's.
ADR-0018 also considered neutralizing them and rejected it,
on the grounds that they would install for an agent that has its own copy beside its plugin and no use for a second one.
That objection assumed the per-target skills it was defending.
With one shared skill, the neutral copies have exactly one real consumer — that skill —
and the copy beside the plugin serves a different consumer, the plugin's own `import.meta.url` resolution.
Two copies, two consumers.

**"It corrupts consumer detection."**
It did, because Codex was inferred from the skill file.
The inference existed to protect neutral payloads that were Codex's.
They are shared now, so the inference is removed and Codex is read from its hook entry,
which is the signal that actually means "Codex has an integration installed".
The removal question is answered by a second, conservative predicate rather than by that one.

**"It makes uninstall unresolvable."**
The refcounting it feared is one comparison, and review confirmed it converges in either order.
What ADR-0018 did not foresee is that the comparison must be conservative rather than merely correct,
because it now authorises a delete.
That is a constraint on the rule, not a reason the rule cannot exist.

The cost ADR-0018 accepted — two copies of every skill on every dual-agent machine — is what this change spends to answer them.

## Out of scope

- Claude Code, which the marketplace owns and `semlf` never touches.
  A user who symlinks `~/.claude/skills/semantic-linefeeds` into the shared root gets the shared copy;
  that is their arrangement, and this design neither creates nor removes it.
- Creating symlinks in any agent's own skills root.
  An earlier draft did; the findings above record why it was dropped.
- Project-level `.opencode/skill` and `.opencode/skills`, which outrank the shared root and are not inspected.
- The opencode command file, which is not a skill and collides with nothing.
- Teaching the opencode plugin to read the neutral checker instead of its own.
- Any change to what the hook reports, or to detector behavior.
- Any change to how install preflights, refuses, backs up, or records ordinary file artifacts,
  with the one exception named above:
  a legacy skill file that no record proves is refused rather than forcibly removed.
