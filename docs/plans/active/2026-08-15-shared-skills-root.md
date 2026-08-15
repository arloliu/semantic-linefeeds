# One skill, one copy, and a link in every agent's own root

**Date:** 2026-08-15
**Status:** in review — revised after one round of external review, no code written yet
**Answers:** [the neutral-ownership handoff](2026-08-15-neutral-ownership-handoff.md)
**Supersedes:** [ADR-0018](../../decisions/0018-skills-ship-per-target.md), whose objections are answered at the end

## What this changes

A skill is published **once**, to `~/.agents/skills`,
and each agent that keeps its own skills root gets a **symlink** there pointing at that one copy.

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

**opencode's own root wins, so a stale copy shadows a fresh one.**
This is measured, not assumed (see the findings below).
A machine that installed opencode's skill under the old layout,
and then upgrades to a layout that publishes only the shared copy,
would keep loading last release's skill forever.

**Duplication with nothing to show for it.**
Two identical setup skills on every dual-agent machine, from one source, indefinitely.

## Verified findings

Each was checked on 2026-08-15 against the installed binary or the source, and each one shaped the design.

### opencode deduplicates skills by name, and its own root wins

`opencode debug skill` lists every skill opencode resolves, as JSON.
On a machine whose `~/.config/opencode/skills` is a symlink to `~/.agents/skills`,
it reports 30 skills and **no duplicate names**,
so a skill reachable by two paths is advertised once.

Precedence was measured in isolation rather than inferred from that machine, where both roots are one inode.
With a distinct `ztest` skill placed in each of two separate roots,
opencode reports exactly one, and it is the copy under its own root.

Two consequences.
A link in opencode's own root does not double-advertise anything, so the link is safe.
And a stale real file in that root silently defeats a correct shared copy,
which is why migration must remove those files rather than merely stop writing them.

### A leaf symlink resolves correctly

`~/.config/opencode/skills/<name>` pointing at `~/.agents/skills/<name>` was tested directly:
opencode resolves it, reports the canonical location, and still counts it once.
This is the exact shape this design installs.

### Precedence is a race, and it covers only the global roots

"Own root wins" is an observed outcome, not a rule opencode publishes.
`loadSkills` adds every discovered match with unbounded concurrency, so the last add to complete wins,
and config directories are scanned after external ones, which is why their adds tend to land last.
Rather than documenting a precedence,
opencode's own troubleshooting page tells users to keep skill names unique across locations.

The claim also holds only for the global roots.
Effective order puts a project-level `.opencode/skill` or `.opencode/skills` above every global root,
so a project-level copy outranks the shared one, and nothing in this design looks there.
That is a stated carve-out rather than a case this design handles,
and it is the same blind spot `_judgment_layer_present` already has.

The migration reasoning does not depend on the distinction.
Whether a stale copy in opencode's own root shadows the shared one deterministically or by winning a race,
it is a hazard, and removing it is the answer either way.

### A second discovery path costs a warning per session

opencode does not silently deduplicate.
`add` overwrites the name-keyed record and logs `duplicate skill name` each time the same name arrives from another path.

Measured on this machine:
2586 such warnings across 53 runs, between 30 and 57 per run,
of which 1074 have exactly the shape a link produces —
`existing=~/.agents/skills/<name>/SKILL.md duplicate=~/.config/opencode/skills/<name>/SKILL.md`.

Those particular warnings are not this design's doing.
This machine's opencode skills root is already a symlink to the shared root,
so every skill there is discovered twice by two spellings, and 29 of them belong to another tool.

What this design adds is narrower, and it is worth stating exactly.
On a machine whose roots are **not** joined, each installed link creates a second discovery path for one skill,
so opencode logs two extra warnings per session — one per linked skill.
On a machine whose roots **are** joined, no link is created at all, so it adds none.

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
The canonical copies are therefore safe from another tool's sync.

The remaining exposure is a name collision:
that tool's own canonical write lands over ours
when a user runs `skills add` for something named `semantic-linefeeds` or `setup-semlf`.
That is user-initiated and out of this design's reach;
`semlf doctor` reports the resulting mismatch, which is the right outcome.

### The reference implementation confirms two rules and contradicts one

`createSymlink` in that same bundle is this design's mechanism, arrived at independently.
It returns early when the real target and the real link path are equal,
and again when their parent-symlink resolutions are equal —
the "already resolves to canonical, do nothing" rule.
Its removal path detects installed agents, excludes the ones being removed,
and deletes the canonical copy only when none remain — the last-consumer rule.

It diverges in two ways this design does not follow.
It writes a relative link, where this design writes an absolute one (the reason is below).
And when something else occupies the link path it deletes that recursively,
where this design refuses.

It also demonstrates why the realpath guard here is not hypothetical.
Its per-agent cleanup skips the canonical path by **string equality**,
so an agent path that resolves to the canonical directory by a different spelling is not recognised,
and is removed recursively.

### The hook's judgment-layer probe needs no change

`_judgment_layer_present` in `scripts/check_linefeeds.py` already probes `$HOME/.agents/skills/semantic-linefeeds/SKILL.md`,
which is the canonical destination,
and `_looks_like_the_skill` opens candidates with `open()`, which follows symlinks.
So opencode's candidate keeps answering `True` through the installed link,
and no detector behavior changes.

### `opencode-readme` has no consumer other than the opencode skill

Nothing under `adapters/opencode/` references a README.
That row exists only so the opencode skill's suppression link resolves offline.
Once one shared skill cites the neutral README, the row is an orphan.

### The opencode plugin genuinely needs its own checker

`adapters/opencode/semantic-linefeeds.ts:76` resolves `./check_linefeeds.py` through `import.meta.url`,
so the copy beside the plugin is load-bearing and stays.
A dual-agent machine therefore carries two checkers.

### Removal of a file refuses anything that is not a regular file

`plan_remove_file` refuses a directory and refuses a non-regular file (`lifecycle.py:988-1000`).
A link therefore needs its own planner rather than a flag on that one.

That function also unlinks its destination unconditionally once `--force` admits it.
On a machine whose opencode skills root is joined to the canonical root,
that path is the canonical file, so a forced removal would delete it through the parent symlink.
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
publish the checker inside the skill directory and cite it relatively, so it travels through the same link.
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
and every ambiguity resolves to *yes*:
an unreadable or unparseable `hooks.json` counts as Codex present, not absent.
`plan_remove_codex_hook` already draws that line for the hook itself (`lifecycle.py:1067`),
and this is the same discipline applied to the question that now authorises a delete.

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

| id | owner | destination | kind |
|---|---|---|---|
| `checker` | `shared` (was `codex`) | `~/.local/share/semlf/check_linefeeds.py` | file |
| `readme` | `shared` (was `codex`) | `~/.local/share/semlf/README.md` | file |
| `skill` (was `codex-skill`) | `shared` (was `codex`) | `~/.agents/skills/semantic-linefeeds/SKILL.md` | file |
| `setup-skill` (was `codex-setup-skill`) | `shared` (was `codex`) | `~/.agents/skills/setup-semlf/SKILL.md` | file |
| `codex-hook-template` | `codex` | `$CODEX_HOME/hooks.json` | hook merge |
| `opencode-plugin` | `opencode` | `…/opencode/plugins/semantic-linefeeds.ts` | file |
| `opencode-checker` | `opencode` | `…/opencode/plugins/check_linefeeds.py` | file |
| `opencode-skill-link` | `opencode` | `…/opencode/skills/semantic-linefeeds` | link |
| `opencode-setup-skill-link` | `opencode` | `…/opencode/skills/setup-semlf` | link |
| `opencode-setup-command` | `opencode` | `…/opencode/commands/setup-semlf.md` | file |
| `agentsmd-snippet` | `agentsmd` | user-named | snippet |

Rows removed: `opencode-skill` and `opencode-setup-skill`, replaced by the canonical copy plus a link;
`opencode-readme`, which has no consumer left.

Codex gets no link row.
The canonical root is the directory Codex already reads, so it holds the real file.

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

### Link rows are not payload rows

`PayloadRow` describes a payload: a source file, an embedded member path, and a rendering.
A link has none of those, and every packaging consumer assumes they exist:

- `registry.stage_payloads` reads `row.source` and writes `row.member` for every row.
- The zipapp builder and the wheel build hook both call it,
  and `tests/test_packaging.py` asserts each row's member is present in the built artifact.
- `tests/test_installer.py`'s checkout fixtures assume every row has a real source file.
- `payload_destinations()` and `plan_install` both filter on `row.recorded`.

So link rows are represented explicitly as non-payload rows and excluded from the payload paths,
rather than added to the table and left to break staging.
The registry test that pins ids, owners, members, the unrecorded set, and the identity set changes with them.

## The link

**A link points at the canonical directory, by absolute path.**

Directory rather than `SKILL.md`:
one link then covers whatever else a skill directory grows,
and opencode was measured resolving exactly this shape.

Absolute rather than the relative form `mattpocock/skills` writes.
A relative link is always computable, so that is not the reason;
the reason is consistency with the rest of the installer,
which records absolute destinations and writes absolute paths into the hook and the skill body.
A relative link would survive a moved home directory,
but nothing else semlf installs would, so the property buys nothing on its own.

### The states a link destination can be in, in this order

The order matters, and getting it wrong breaks the design's own headline case.

1. **Its real path equals the canonical directory's real path** — do nothing.
2. **Absent** — create the symlink.
3. **A file this kit installed under the old layout, provable from its record** — migrate it (see below).
4. **Anything else** — refuse, naming the path.

Testing equality before absence is not a style choice.
On a joined root, before anything is installed,
`os.path.lexists` on the link path is false, because the leaf does not exist yet.
Absence would be read first, a symlink would be planned,
and by the time it applied the canonical row would already have created that same directory through the parent symlink —
so `os.symlink` would raise `FileExistsError` mid-apply.
`os.path.realpath` resolves a parent symlink even when the final component is missing,
so testing it first sees the truth and plans nothing.

The comparison is `realpath` on **both** sides.
A canonical root that is itself a symlink — `~/.agents/skills` pointing at `/opt/skills`, say —
is a valid arrangement, and comparing a resolved link against an unresolved canonical string would refuse it.

This is what makes every symlink topology work rather than one named pattern:
`realpath` collapses a root symlink, a leaf symlink, and any intermediate symlink alike.
A user who has already arranged their roots gets a no-op, not a refusal and not a second copy.

Bind mounts are the stated exception.
`realpath` does not cross a bind mount, so a bind-mounted skills root reads as unrelated and is refused.
Detecting it would need device and inode comparison, which is a different mechanism;
refusing is the safe outcome and the refusal names the path.

The fourth state is the precision rule.
`--force` does not widen it into permission to delete a directory of someone else's files.
Backup-and-replace is deliberately not offered there:
the thing to back up is a directory, and `exclusive_backup` is a single-file byte-level primitive.

### Links are recorded

An earlier draft left links out of the provenance manifest,
arguing that a symlink carries its own evidence.
That argument is wrong, and the review that found it is worth restating:
`lstat` and `readlink` prove *what* a path currently is, not *who* created it.

The failure is concrete.
A user, or `mattpocock/skills`, creates exactly the leaf link this design would create.
Install sees state 1 and correctly does nothing.
`semlf uninstall opencode` then deletes a link semlf never made.

So a link row gets a record like every other artifact,
in a link-shaped variant of the existing entry: the link's own path, the target it was created with, and the version.
`manifest._valid_entry` gains that shape beside the digest shape,
and a link classifies as managed when the path is a symlink whose recorded target still matches.

Removal then requires all three:
the path is itself a symlink, its record proves semlf created it, and it resolves to the canonical directory.
Without a record it is left alone, which is the correct answer for a link the user made.

Install's state 1 writes the record when the existing link already matches what we would have created,
which is the same adoption `classify_artifact` performs for a file whose bytes already equal the rendering.
A link that resolves to canonical only through a parent symlink is not adopted and not recorded:
there is no leaf link there to own.

### A machine that cannot create symlinks is not a failed install

`os.symlink` fails without privilege on Windows.
The reference implementation sidesteps this by creating a directory junction, which needs no privilege;
Python's standard library has no junction API, and the CLI stays stdlib-only,
so that route would mean shelling out to `mklink` and is not taken.

The link rows therefore print a note and the install continues, with a zero exit code.
Both targets read the canonical root natively,
so an install without the links is correct and usable;
the link buys the shadowing protection, not the skill's reachability.

Two mechanisms have to cooperate for that to actually be true.
`apply_plan` treats a returned note as an error and exits 1 (`lifecycle.py:247-249`),
so the link's own apply step must catch the `OSError`, print its note, and return `None`.
And `doctor` must not fail the machine for the absent link,
which the link states below handle.

## Install

Selection becomes:

- `row.owner in targets` for the target-owned rows, unchanged.
- `row.owner == "shared"` when at least one agent target is selected.

`agentsmd` alone selects no shared row.
It is a paragraph of text with no checker and no skill behind it.

## Uninstall

Per-target removal keeps its shape, with three additions.

**Links** get their own planner, because `plan_remove_file` refuses any non-regular destination.
Removing `opencode` inspects each link path:

- the path is itself a symlink, its record proves semlf created it,
  and it resolves to the canonical directory — remove it;
- the path resolves to the canonical directory but is not itself a symlink, because a parent is —
  do nothing, since removing it would delete the canonical directory's contents;
- anything else, including a matching link with no record — leave it alone.

The new planner must not inherit `plan_remove_file`'s forced unlink.
`--force` widens which provenance states are admissible;
it never makes it acceptable to unlink a path that resolves into the canonical directory.

**Last consumer**, by the conservative rule stated earlier, with those removals planned last.

**Legacy rows.**
Uninstall must remove the pre-change artifacts too, not only the new ones.
Upgrading the package and immediately running `semlf uninstall opencode` is a reachable path,
and it never runs an install under the new layout.
Without this, the old judgment skill, the old setup skill, and the plugin README survive an uninstall that reported success —
and because opencode's own root wins, the stale skill stays advertised.
The converse holds for Codex:
a legacy skill proven only by a `codex-skill` record must not refuse removal because the new plan asks for `skill`.
`tests/test_migration.py` already pins direct uninstall of an old recorded skill, and that contract is kept.

`checker` and `readme` are retained and named by `status`, as they are today.
The closing note about retained shared payloads now prints whenever any were retained, not only for `codex`,
and it must print from **both** doors —
`scripts/install.py`'s uninstall returns straight from `apply_plan` today and has no such note.

## The collision refusal

`colliding_destinations` keeps its purpose but not its selection test, which is covered above.

The collision it was originally written for stops existing:
there is one skill row, and one row cannot collide with itself.
A link row cannot trip it either —
a link's destination is a directory and the canonical row's destination is a file inside that directory,
so their real paths are never equal.

What it still covers is `checker` against `opencode-checker`,
joined when someone points the plugins directory at the data root.
That still deserves a refusal:
the bytes match, but two provenance records would name one file,
and `uninstall opencode` would delete the copy the other integration depends on.

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
and a retired record proves a file at the same resolved path,
the projection presents that record under the new name.
Classification then sees a managed artifact and plans a normal replace,
`--dry-run` describes it truthfully,
and apply writes the new record and forgets the retired one.

Without this, an ordinary upgrade stops at a wall.
`classify_artifact` adopts only when the bytes already equal the rendering,
so a machine whose `SKILL.md` is unchanged would survive anyway;
a release that changed `SKILL.md` would classify the file as unrecorded and refuse without `--force`.
That case is not hypothetical on a joined root:
the canonical path there may hold the **opencode** rendering, which cites the plugins directory,
so its bytes differ from the shared rendering by construction.

### What migration does to each pre-change state

| Pre-change state | Action |
|---|---|
| `~/.agents/skills/…/SKILL.md` recorded as `codex-skill` | project the record onto `skill`, publish normally, then forget the retired record |
| the same, recorded as `codex-setup-skill` | the same, onto `setup-skill` |
| a real `…/opencode/skills/…/SKILL.md` whose record proves it, whose real path differs from the canonical file | remove it, prune its now-empty directory, forget the record, create the link |
| the same, but whose real path **equals** the canonical file | project the record onto `skill` or `setup-skill`; never remove the file |
| `…/opencode/plugins/README.md` whose record proves it | remove it, forget the record |
| any of those paths holding content no record proves | refuse, naming the path |

The fourth row is the trap this whole design has to survive.
On a machine whose opencode skills root is a symlink into `~/.agents/skills`,
the old `opencode-skill` record's path resolves to the canonical file itself.
A migration that removes whatever provenance proves is ours would delete the canonical copy.
So the condition is provable **and** not the canonical file,
and the record is carried forward rather than merely forgotten.

The third row must prune the emptied directory.
The old layout created `…/opencode/skills/semantic-linefeeds/` as a real directory holding `SKILL.md`;
removing only the file leaves the directory, and `os.symlink` cannot create a link where a directory already sits.

### Ordering, and the states that have no rollback

Publication of the canonical file and its new record comes **before** any destructive legacy cleanup.
`apply_plan` has no rollback: it stops at the first error and reports what was and was not applied,
so the only safe order is the one where an interruption leaves the canonical copy present.

These partial states are reachable and each must converge on a re-run rather than refuse:

- a retired record exists but its destination is gone;
- the legacy file is gone but clearing its record failed;
- both a retired and a new record exist;
- a new record exists while the retired one remains;
- the legacy file was removed before canonical publication, or before link creation, succeeded.

### `--force` loses a recovery path, and that is a contract change

Today a legacy `SKILL.md` whose record is missing or corrupt can still be repaired:
`classify_artifact` backs it up and replaces it under `--force`.
Under this design the same machine meets a refusal instead,
because the object at the link path is a directory and directories are not backed up.

That is the intended precision trade, but it is user-visible,
so it is stated here rather than left under an out-of-scope claim that install's force behavior is unchanged.

## Status and doctor

The literal `(name, label)` loop `status_command` walks gains `skill`, `setup-skill`,
and the two link rows, and loses the removed rows.
A link cannot go through the file path in that loop:
it renders no bytes, and `object_state` would report a correct link as a non-regular file.
Link rows report their own states.

`doctor` needs the same vocabulary, with three distinct outcomes,
because "doctor exits clean" is not a contract about corrupted states:

- **link absent** — informational, never a failure.
  This is what an unprivileged Windows machine looks like, and that install is correct.
- **link present and resolving to the canonical directory** — healthy.
- **link path occupied by something else, or a real directory shadowing the canonical copy** — a failure with the path named.

The third case is the one `doctor` is blind to today,
and it is the exact state that makes opencode load last release's skill.

Shared payload expectedness in both verbs changes as described in the registry section.

## Testing

Pinned by the suite:

- Both topologies, each with both targets and with one target alone:
  a root-directory symlink, and a per-skill leaf symlink.
- A joined root on a machine with nothing installed —
  the case where testing absence before real-path equality would fail mid-apply.
- A canonical root that is itself a symlink.
- Sequential installs — `install codex` today, `install opencode` tomorrow.
  Every existing case installs both in one command,
  so the path where the second install meets the first one's files has no coverage.
- A user-created leaf link is adopted by install and **not** removed by uninstall when no record proves it.
- An opencode-only install now **does** create the neutral root,
  which inverts the assertion at `tests/test_semlf_install.py:160`,
  and the checker the installed skill cites is present.
- Removing one target leaves the other's install whole;
  removing the last one takes the canonical skills and retains the checker and README.
- The conservative removal predicate: an unreadable `hooks.json` retains the shared skills.
- `uninstall opencode` on a joined root deletes nothing through the link path, with and without `--force`.
- Uninstall of a legacy machine that never ran an install under the new layout.
- Migration from the pre-change layout, in both the separate-roots and joined-root variants,
  including the joined-root machine whose canonical file holds the old opencode rendering.
- Each partial migration state converges on a re-run.
- `prune_parent` prunes only the skill's own directory and only when it is empty.
  A shared root routinely holds other tools' skills, so an over-eager prune is a large loss.
- A failing `os.symlink` prints its note and leaves the exit code at zero.
- `doctor` reports the three link states distinctly, and fails on a shadowing directory.
- The registry coupling tests, covering ids, owners, members, and the unrecorded and identity sets.
- Packaging's per-row member assertions, which link rows must not break.

Not reachable from pytest, and verified by running the real agents:
installing from the checkout and asking a real Codex and a real opencode to load the skill and quote a rule back.

## Records and documentation

- **ADR-0019** supersedes ADR-0018 and answers its objections.
- It amends [ADR-0016](../../decisions/0016-one-entry-point-and-the-payload-registry.md):
  `owner` may be `shared`, meaning any selected agent target,
  and a row may describe a link rather than a payload.
- It extends [ADR-0014](../../decisions/0014-lifecycle-verbs-and-the-provenance-manifest.md)
  with the link-shaped record, and records why self-evidence was not enough.
- The README section listing install destinations is updated.
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
The refcounting it feared is one comparison, and the review confirmed it converges in either order.
What ADR-0018 did not foresee is that the comparison must be conservative rather than merely correct,
because it now authorises a delete.
That is a constraint on the rule, not a reason the rule cannot exist.

The cost ADR-0018 accepted — two copies of every skill on every dual-agent machine — is what this change spends to answer them.

## Out of scope

- Claude Code, which the marketplace owns and `semlf` never touches.
  A user who symlinks `~/.claude/skills/semantic-linefeeds` into the shared root gets the canonical copy;
  that is their arrangement, and this design neither creates nor removes it.
- The opencode command file, which is not a skill and collides with nothing.
- Teaching the opencode plugin to read the neutral checker instead of its own.
- Any change to what the hook reports, or to detector behavior.
- Any change to how install preflights, refuses, backs up, or records ordinary file artifacts,
  with the one exception named above:
  a legacy skill directory that no record proves is refused rather than backed up and replaced.
