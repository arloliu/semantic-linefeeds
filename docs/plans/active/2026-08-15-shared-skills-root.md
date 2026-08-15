# One skill, one copy, and a link in every agent's own root

**Date:** 2026-08-15
**Status:** approved — no code written yet
**Answers:** [the neutral-ownership handoff](2026-08-15-neutral-ownership-handoff.md)
**Supersedes:** [ADR-0018](../../decisions/0018-skills-ship-per-target.md), whose three objections are answered in the last section

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

### 2. Consumer inference

`installed_consumers()` counts Codex as installed when its skill file is present.
Its docstring gives the reason:
the skill references the neutral checker and README,
so removing only the hook must not downgrade those payloads to leftovers.

Making them shared rows dissolves that reason.
They are no longer Codex's, and their consumer is any installed integration.

**Decision: Codex is inferred from its owned hook entry alone.**
opencode is inferred from its plugin file, unchanged.
This is also what stops an opencode-only machine from inventing a Codex consumer,
which was ADR-0018's second objection to a shared root.

### 3. Last-consumer uninstall

**Decision: the two shared skills are removed when the last consumer goes.**
`checker` and `readme` keep the retain-and-report precedent.

The asymmetry is deliberate and it is about behavior, not tidiness.
A checker left behind does nothing until something calls it.
A skill left behind is still advertised to every model that scans the root,
and the checker path in its body may by then point at nothing.

Refcounting is not an extra cost here.
The link layer already forces a "who else points at this" question on every removal,
so the last-consumer rule is the same code rather than a second mechanism.

### 4. Migration

Covered in its own section below.
The joined-root case is the trap, and it is stated there explicitly.

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

## The link

**A link points at the canonical directory, by absolute path.**

Directory rather than `SKILL.md`:
one link then covers whatever else a skill directory grows,
and opencode was measured resolving exactly this shape.

Absolute rather than the relative form `mattpocock/skills` writes:
`XDG_CONFIG_HOME` is not guaranteed to sit under `$HOME`,
so a relative link cannot always be computed into something sane.

### The four states a link destination can be in

| Existing state | Action |
|---|---|
| absent | create the symlink |
| already resolves to the canonical directory | do nothing |
| a file this kit installed under the old layout, provable from its record | remove it, then create the symlink |
| anything else | refuse, naming the path |

The second row is what makes every symlink topology work rather than one named pattern.
It is keyed on `os.path.realpath`, which collapses a root symlink, a leaf symlink,
and any intermediate symlink alike.
A user who has already arranged their roots gets a no-op, not a refusal and not a second copy.

The last row is the precision rule.
`--force` does not widen it into permission to delete a directory of someone else's files.
Backup-and-replace is deliberately not offered here:
the thing to back up is a directory, and `exclusive_backup` is a single-file byte-level primitive.

### Links are not recorded in the provenance manifest

This is a stated exception to [ADR-0014](../../decisions/0014-lifecycle-verbs-and-the-provenance-manifest.md).

A record exists to prove that bytes at a path are ours, so replacing or removing them is safe.
A symlink carries that proof itself:
`lstat` and `readlink` answer whether the path is a symlink and where it points,
and they answer about the state on disk right now rather than about a recording that may have gone stale.
The removal test is therefore stronger than a digest record would be —
**the path is itself a symlink, and it resolves to our canonical directory.**

The consequence is that `status` reports links by inspection.
That is the better report, since it describes what is on disk.

### A machine that cannot create symlinks is not a failed install

`os.symlink` fails without privilege on Windows.
The link rows then print a note and the install continues, with a zero exit code.

This is honest rather than lenient.
Both targets read the canonical root natively,
so an install without the links is correct and usable;
the link buys the shadowing protection, not the skill's reachability.
Turning an optional protection into a fatal error would block an install that works.

## Install

Selection becomes:

- `row.owner in targets` for the target-owned rows, unchanged.
- `row.owner == "shared"` when at least one agent target is selected.

`agentsmd` alone selects no shared row.
It is a paragraph of text with no checker and no skill behind it.

## Uninstall

Per-target removal keeps its shape, with two additions.

**Links.**
Removing `opencode` inspects each link path:

- the path is itself a symlink resolving to the canonical directory — remove it;
- the path resolves to the canonical directory but is not itself a symlink, because a parent is —
  do nothing, since removing it would delete the canonical directory's contents;
- anything else — leave it alone, it is not ours.

**Last consumer.**
The plan computes `installed_consumers()` minus the targets being removed.
When nothing remains, `skill` and `setup-skill` join the removal plan.
`checker` and `readme` are retained and named by `status`, as they are today.
The closing note about retained shared payloads now prints whenever any were retained, not only for `codex`.

## The collision refusal

`colliding_destinations` is not replaced by a smarter refusal.
The collision it was written for stops existing:
there is one skill row, and one row cannot collide with itself.

A link row cannot trip it either.
A link's destination is a directory and the canonical row's destination is a file inside that directory,
so their real paths are never equal.

What the check still covers is `checker` against `opencode-checker`,
joined when someone points the plugins directory at the data root.
That still deserves a refusal:
the bytes match, but two provenance records would name one file,
and `uninstall opencode` would delete the copy the other integration depends on.

## Migration

Everything below is planned and disclosed like any other work.
It appears in `--dry-run` output; none of it is a silent side effect of install.

| Pre-change state | Action |
|---|---|
| `~/.agents/skills/…/SKILL.md` recorded as `codex-skill` | rename the record to `skill`; the file and path are unchanged |
| the same, recorded as `codex-setup-skill` | rename the record to `setup-skill` |
| a real `…/opencode/skills/…/SKILL.md` whose record proves it, whose real path differs from the canonical file | remove it, forget the record, create the link |
| the same, but whose real path **equals** the canonical file | keep the file, forget the record |
| `…/opencode/plugins/README.md` whose record proves it | remove it, forget the record |
| any of those paths holding content no record proves | refuse, naming the path |

The fourth row is the trap this whole design has to survive.
On a machine whose opencode skills root is a symlink into `~/.agents/skills`,
the old `opencode-skill` record's path resolves to the canonical file itself.
A migration that removes whatever provenance proves is ours would delete the canonical copy.
So the condition is provable **and** not the canonical file.

Renaming records is not cosmetic.
`classify_artifact` adopts a destination whose bytes already equal the rendering,
so a machine whose `SKILL.md` has not changed would survive without the rename.
A release that changes `SKILL.md` would not:
the new row name has no record, provenance reads `unrecorded`, and install refuses without `--force`.
The rename step — carry the old record's fields to the new name when the new name has none, then forget the old —
is what keeps an upgrade from stopping at a wall.

## Status

The literal `(name, label)` loop `status_command` walks gains `skill`, `setup-skill`,
and the two link rows, and loses the removed rows.

Shared payload expectedness changes with the owner model.
`doctor.py`'s `expected = row.owner in consumers` becomes `expected = bool(consumers)` for a shared row:
any installed integration makes a shared payload expected,
and only a machine with no integrations at all reports one as a leftover.
`status` carries the same change in its own comparison.

Link rows report by inspection:
installed and pointing at the canonical directory, absent, or occupied by something else.

## Testing

Pinned by the suite:

- Both topologies, each with both targets and with one target alone:
  a root-directory symlink, and a per-skill leaf symlink.
- Sequential installs — `install codex` today, `install opencode` tomorrow.
  Every existing case installs both in one command,
  so the path where the second install meets the first one's files has no coverage.
- An opencode-only install now **does** create the neutral root,
  which inverts the assertion at `tests/test_semlf_install.py:160`,
  and the checker the installed skill cites is present.
- Removing one target leaves the other's install whole;
  removing the last one takes the canonical skills and retains the checker and README.
- `uninstall opencode` on a joined root deletes nothing through the link path.
- Migration from the pre-change layout, in both the separate-roots and joined-root variants.
- `prune_parent` prunes only the skill's own directory and only when it is empty.
  A shared root routinely holds other tools' skills, so an over-eager prune is a large loss.
- A failing `os.symlink` prints its note and leaves the exit code at zero.
- `doctor` exits clean after each scenario.
- The `KNOWN`-versus-registry coupling test follows the row changes.

Not reachable from pytest, and verified by running the real agents:
installing from the checkout and asking a real Codex and a real opencode to load the skill and quote a rule back.

## Records and documentation

- **ADR-0019** supersedes ADR-0018 and answers its three objections.
- It amends [ADR-0016](../../decisions/0016-one-entry-point-and-the-payload-registry.md):
  `owner` may be `shared`, meaning any selected agent target.
- It records the ADR-0014 exception for links, with the self-evidence reason.
- The README section listing install destinations is updated.
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

**"It makes uninstall unresolvable."**
The refcounting it feared is one comparison:
the consumers still present after this removal.
The link layer forces that same question anyway,
so it is one rule serving two purposes rather than a mechanism added for this one.

The cost ADR-0018 accepted — two copies of every skill on every dual-agent machine — is what this change spends to answer them.

## Out of scope

- Claude Code, which the marketplace owns and `semlf` never touches.
  A user who symlinks `~/.claude/skills/semantic-linefeeds` into the shared root gets the canonical copy;
  that is their arrangement, and this design neither creates nor removes it.
- The opencode command file, which is not a skill and collides with nothing.
- Teaching the opencode plugin to read the neutral checker instead of its own.
- Any change to what the hook reports, or to detector behavior.
- Any change to how install preflights, refuses, backs up, or records file artifacts.
